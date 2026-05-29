"""
SkillWeaver provider for unified memory system
"""

import os
import importlib.util
import uuid
import re
import ast
import inspect
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable

from module_memory.base_memory import BaseMemoryProvider, atomic_write_text, file_lock
from module_memory.memory_types import (
    MemoryRequest,
    MemoryResponse,
    TrajectoryData,
    MemoryType,
    MemoryItem,
    MemoryItemType,
    MemoryStatus
)

# Import unified tool wrapper
from storage.tools.tool_wrapper import ToolWrapper


class MemoryProvider(BaseMemoryProvider):
    """
    SkillWeaver memory provider that manages generated skills
    """
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.SKILLWEAVER, config)
        
        # Configuration
        self.skills_file_path = self.config.get(
            "skills_file_path",
            "./storage/skillweaver/skillweaver_generated_skills.py",
        )
        # Optional skills directory: load all *.py files if provided
        self.skills_dir = self.config.get("skills_dir", "./storage/skillweaver")
        
        # Optional model used directly for LLM-driven code generation
        self.model = self.config.get("model")
        
        # Skills registry
        self.skills_registry: Dict[str, Callable] = {}
        self.skills_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [SkillWeaver] [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Initialize unified tool wrapper
        self.tool_wrapper = ToolWrapper(model=self.model, logger=self.logger)
    
    def initialize(self) -> bool:
        """Initialize SkillWeaver provider by loading existing skills"""
        try:
            # Ensure storage directories exist
            if self.skills_dir:
                os.makedirs(self.skills_dir, exist_ok=True)
            parent_dir = os.path.dirname(self.skills_file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            # Prefer loading from directory when available, else fallback to single file
            if os.path.isdir(self.skills_dir):
                self._load_skills_from_dir(self.skills_dir)
            elif os.path.exists(self.skills_file_path):
                self._load_skills_from_file(self.skills_file_path)
            # If neither exists, still return True to allow future ingestion to create files
            return True
        except Exception as e:
            print(f"Error initializing SkillWeaver provider: {e}")
            return False
    
    def _load_skills_from_file(self, file_path: str):
        """Load skills from a single generated skills file"""
        try:
            spec = importlib.util.spec_from_file_location("skillweaver_skills", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._populate_registry_from_module(module)
        except Exception as e:
            print(f"Error loading skills from file {file_path}: {e}")
    
    def _load_skills_from_dir(self, dir_path: str):
        """Load skills from all .py files in a directory"""
        try:
            for filename in os.listdir(dir_path):
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                file_path = os.path.join(dir_path, filename)
                try:
                    spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._populate_registry_from_module(module)
                except Exception as inner_e:
                    print(f"Error loading skills from {file_path}: {inner_e}")
        except Exception as e:
            print(f"Error scanning skills directory {dir_path}: {e}")
    
    def _populate_registry_from_module(self, module):
        """Extract public callables from a module as skills and capture their metadata"""
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if callable(obj):
                self.skills_registry[name] = obj
                docstring = getattr(obj, "__doc__", "") or ""
                self.skills_metadata[name] = {
                    "description": (docstring.split("\n")[0] if docstring else name),
                    "full_docstring": docstring,
                    "module": getattr(module, "__name__", "skillweaver_skills"),
                }
    
    def _reload_skills(self):
        """Reload skills after ingestion"""
        self.skills_registry.clear()
        self.skills_metadata.clear()
        self.tool_wrapper.clear_cache()  # Clear tool wrapper cache when reloading
        if os.path.isdir(self.skills_dir):
            self._load_skills_from_dir(self.skills_dir)
        elif os.path.exists(self.skills_file_path):
            self._load_skills_from_file(self.skills_file_path)
    
    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Provide memory by searching for relevant skills
        """
        try:
            if request.status != MemoryStatus.BEGIN:
                return MemoryResponse(
                    memories=[],
                    memory_type=self.memory_type,
                    total_count=0,
                    request_id=str(uuid.uuid4()),
                )

            # Simple keyword matching for skills
            relevant_skills = []
            query_lower = request.query.lower()
            
            for skill_name, metadata in self.skills_metadata.items():
                description = metadata.get("description", "").lower()
                docstring = metadata.get("full_docstring", "").lower()
                
                # Score based on keyword matches
                score = 0.0
                for word in query_lower.split():
                    if word in skill_name.lower():
                        score += 2.0
                    elif word in description:
                        score += 1.5
                    elif word in docstring:
                        score += 1.0
                
                if score > 0:
                    relevant_skills.append({
                        "skill_name": skill_name,
                        "metadata": metadata,
                        "score": score,
                    })
            
            # Sort by score and take top results
            relevant_skills.sort(key=lambda x: x["score"], reverse=True)
            top_skills = relevant_skills[:3]
            
            # Convert to MemoryItem format
            memories: List[MemoryItem] = []
            for skill_info in top_skills:
                skill_name = skill_info["skill_name"]
                function_obj = self.skills_registry.get(skill_name)
                if not function_obj:
                    continue
                content = self._format_skill_content(skill_name, skill_info["metadata"], request.status)
                
                # Wrap function as a runtime tool
                wrapped_tool = self._wrap_tool(function_obj, skill_name)
                
                memory_item = MemoryItem(
                    id=f"skill_{skill_name}",
                    content=content,
                    metadata={
                        "skill_name": skill_name,
                        "description": skill_info["metadata"].get("description", ""),
                        "score": skill_info["score"],
                        "callable": function_obj,  # Keep original function
                        "wrapped_tool": wrapped_tool,  # Add wrapped tool
                        "status": request.status.value,
                    },
                    score=skill_info["score"],
                    type=MemoryItemType.API,
                )
                memories.append(memory_item)
            
            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4()),
            )
        except Exception as e:
            print(f"Error providing SkillWeaver memory: {e}")
            return MemoryResponse(memories=[], memory_type=self.memory_type, total_count=0)
    
    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Optional[Any]:
        """Wrap Python function as Tool object using unified ToolWrapper"""
        return self.tool_wrapper.wrap_function(tool_func, tool_name)
    
    def _format_skill_content(self, skill_name: str, metadata: Dict, status: MemoryStatus) -> str:
        """Format skill content for API-type memory - content will be handled by main file"""
        try:
            if status == MemoryStatus.BEGIN:
                return f"SkillWeaver Available skill: {skill_name}\nDescription: {metadata.get('description', '')}"
            elif status == MemoryStatus.IN:
                return None  # SkillWeaver only provides memory in BEGIN phase
            return f"SkillWeaver Skill: {skill_name}: {metadata.get('description', '')}"
        except Exception as e:
            print(f"Error formatting skill content: {e}")
            return f"SkillWeaver Skill: {skill_name}"
    
    def _extract_function_from_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Extract the first function from Python code using AST and return its name and the code block."""
        try:
            tree = ast.parse(code)
            func_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            if not func_defs:
                return None
            func = func_defs[0]
            func_name = func.name
            # Best-effort: return the full code as provided (we won't slice exact function body)
            return {"name": func_name, "code": code}
        except Exception:
            return None
    
    def _is_dangerous_code(self, code: str) -> bool:
        """Basic static checks to avoid dangerous operations in generated skills."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Block eval/exec/compile and raw open
                    if isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile", "__import__"}:
                        return True
                    if isinstance(node.func, ast.Name) and node.func.id == "open":
                        return True
                if isinstance(node, ast.Attribute):
                    if node.attr in {"system", "popen", "spawn", "remove", "rmdir"}:
                        return True
            return False
        except Exception:
            return True
    
    def _append_skill_to_file(self, function_name: str, code: str) -> bool:
        """Append skill code to the aggregator file, creating header if needed and avoiding duplicates."""
        try:
            os.makedirs(os.path.dirname(self.skills_file_path) or ".", exist_ok=True)
            with file_lock(self.skills_file_path):
                existing = ""
                if os.path.exists(self.skills_file_path):
                    with open(self.skills_file_path, "r", encoding="utf-8") as f:
                        existing = f.read()
                else:
                    existing = (
                        '"""\nSkillWeaver Generated Skills\nAuto-generated and continuously updated by UnifiedMemory SkillWeaverProvider.\nThis file contains dynamically generated skills.\n"""\n\n'
                    )
                if f"def {function_name}(" in existing:
                    return True
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_content = existing + f"\n# Generated on {timestamp}\n{code}\n\n"
                atomic_write_text(self.skills_file_path, new_content)
            return True
        except Exception as e:
            print(f"Error saving generated skill: {e}")
            return False
    
    def _generate_skill_from_trajectory(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, str]]:
        """Use the injected model to generate a new skill function based on the trajectory."""
        if self.model is None:
            return None
        try:
            # Build prompt (aligned with project conventions)
            trajectory_json = None
            try:
                import json as _json
                trajectory_json = _json.dumps(trajectory_data.trajectory, indent=2, ensure_ascii=False)
            except Exception:
                trajectory_json = str(trajectory_data.trajectory)
            prompt = f"""You are an expert Python programmer specializing in creating reusable, generic functions. Your task is to analyze a successful task execution and extract a GENERAL, PARAMETERIZED skill that can be reused for similar problems.

CRITICAL REQUIREMENTS:
- Create a GENERIC function that accepts parameters, NOT a function that returns hardcoded values
- The function must be REUSABLE for different inputs of the same type of problem
- Focus on the METHODOLOGY and APPROACH, not the specific data from this execution
- Make the function PARAMETERIZED so it can handle various inputs

Original Task:
{trajectory_data.query}

Agent's Successful Trajectory:
```json
{trajectory_json}
```

ANALYSIS INSTRUCTIONS:
1. Identify the CORE METHODOLOGY or ALGORITHM used in the successful execution
2. Abstract away specific values, URLs, names, or data points from this particular task
3. Focus on the GENERAL PATTERN that could apply to similar problems
4. Create a function that takes relevant parameters as input

FUNCTION REQUIREMENTS:
1. Write a single, self-contained Python function that is GENERIC and PARAMETERIZED
2. Use descriptive parameter names and include type hints
3. Include comprehensive docstring with Args and Returns sections
4. Add proper error handling and input validation
5. The function should work for DIFFERENT inputs of the same problem type
6. DO NOT hardcode specific values from this execution - make them parameters instead

EXAMPLE OF GOOD vs BAD:
❌ BAD: def get_population(): return 1234567  # Returns hardcoded value
✅ GOOD: def get_population_from_source(source_url: str, location: str) -> int  # Generic, parameterized

Output ONLY the Python code for this generic function inside a single markdown code block:"""
            messages = [{"role": "user", "content": prompt}]
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            # Extract python code block
            m = re.search(r"```python\n(.*?)```", content, re.DOTALL)
            code = m.group(1).strip() if m else content.strip()
            # Validate
            if self._is_dangerous_code(code):
                return None
            func_info = self._extract_function_from_code(code)
            if not func_info:
                return None
            return {"name": func_info["name"], "code": code}
        except Exception:
            return None
    
    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Ingest new memory by generating new skills from trajectory using the injected model.
        Only extracts skills from trajectories with correct answers to avoid learning bad patterns.
        """
        try:
            # Check if the trajectory has correct answer - only learn from successful cases
            metadata = trajectory_data.metadata or {}
            is_correct = metadata.get("is_correct", False)
            task_success = bool(metadata.get("task_success", metadata.get("is_correct", False)))

            if not is_correct:
                msg = f"SkillWeaverProvider: skipping skill extraction - answer is incorrect (is_correct={is_correct})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            if not task_success:
                msg = f"SkillWeaverProvider: skipping skill extraction - task execution failed (task_success={task_success})"
                print(msg)
                return True, msg  # Return True to not block the pipeline, but don't extract skills

            print(f"SkillWeaverProvider: extracting skill from correct trajectory (is_correct={is_correct}, task_success={task_success})")

            skill = self._generate_skill_from_trajectory(trajectory_data)
            if not skill:
                # No model or failed generation; succeed silently to avoid blocking
                msg = "SkillWeaverProvider: generation skipped (no model or validation failed)"
                print(msg)
                return True, msg

            saved = self._append_skill_to_file(skill["name"], skill["code"])
            if saved:
                self._reload_skills()
                msg = f"SkillWeaverProvider: successfully extracted and saved skill '{skill['name']}' from correct trajectory"
                print(msg)
                absorbed_memory = {
                    "skill_name": skill['name'],
                    "description": skill.get('description', ''),
                    "code": skill['code']
                }
                return saved, f"Generated skill: {absorbed_memory}"
            else:
                return saved, f"Failed to save skill: {skill['name']}"
        except Exception as e:
            error_msg = f"Error taking in SkillWeaver memory: {e}"
            print(error_msg)
            return False, error_msg


SkillWeaverProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.SKILLWEAVER.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "SkillWeaverProvider"]
