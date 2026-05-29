import json
import os
import jieba
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryRequest, 
    MemoryResponse, 
    TrajectoryData, 
    MemoryType, 
    MemoryItem,
    MemoryStatus
)


class MobileEProvider(BaseMemoryProvider):
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.MOBILEE, config)
        
        self.tips_file_path = self.config.get(
            "tips_file_path", 
            "./storage/mobilee/tips/tips.json"
        )
        self.shortcuts_file_path = self.config.get(
            "shortcuts_file_path", 
            "./storage/mobilee/shortcuts/shortcuts.json"
        )
        
        self.model = self.config.get("model")
        
        self.tips: List[str] = []
        self.shortcuts: Dict[str, Dict[str, Any]] = {}
    
    def initialize(self) -> bool:
        try:
            tips_dir = os.path.dirname(self.tips_file_path)
            shortcuts_dir = os.path.dirname(self.shortcuts_file_path)
            if tips_dir:
                os.makedirs(tips_dir, exist_ok=True)
            if shortcuts_dir:
                os.makedirs(shortcuts_dir, exist_ok=True)
            
            if os.path.exists(self.tips_file_path):
                with open(self.tips_file_path, 'r', encoding='utf-8') as f:
                    tips_data = json.load(f)
                    self.tips = tips_data.get('tips', [])
            
            if os.path.exists(self.shortcuts_file_path):
                with open(self.shortcuts_file_path, 'r', encoding='utf-8') as f:
                    self.shortcuts = json.load(f)
            
            return True
            
        except Exception as e:
            print(f"Error initializing MobileE provider: {e}")
            return False

    def _tokenize(self, text: str) -> List[str]:
        return list(jieba.cut_for_search(text))

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        try:
            memories = []
            query_lower = request.query.lower()
            query_tokens = self._tokenize(query_lower)

            relevant_tips = []
            for i, tip in enumerate(self.tips):
                tip_lower = tip.lower()
                score = 0

                for token in query_tokens:
                    token = token.strip()
                    if token and token in tip_lower:
                        score += 1

                if score > 0:
                    relevant_tips.append({
                        'tip': tip,
                        'score': score,
                        'index': i
                    })

            relevant_tips.sort(key=lambda x: x['score'], reverse=True)
            top_tips = relevant_tips[:2] 

            for tip_info in top_tips:
                content = self._format_tip_content(tip_info['tip'], request.status)

                memory_item = MemoryItem(
                    id=f"tip_{tip_info['index']}",
                    content=content,
                    metadata={
                        'type': 'tip',
                        'original_tip': tip_info['tip'],
                        'score': tip_info['score'],
                        'status': request.status.value
                    },
                    score=tip_info['score']
                )
                memories.append(memory_item)

            relevant_shortcuts = []
            for shortcut_name, shortcut_data in self.shortcuts.items():
                description = shortcut_data.get('description', '').lower()
                name_lower = shortcut_name.lower()
                score = 0

                for token in query_tokens:
                    token = token.strip()
                    if not token:
                        continue
                    if token in name_lower:
                        score += 2
                    elif token in description:
                        score += 1

                if score > 0:
                    relevant_shortcuts.append({
                        'name': shortcut_name,
                        'data': shortcut_data,
                        'score': score
                    })

            relevant_shortcuts.sort(key=lambda x: x['score'], reverse=True)
            top_shortcuts = relevant_shortcuts[:2] 

            for shortcut_info in top_shortcuts:
                content = self._format_shortcut_content(
                    shortcut_info['name'],
                    shortcut_info['data'],
                    request.status
                )

                memory_item = MemoryItem(
                    id=f"shortcut_{shortcut_info['name']}",
                    content=content,
                    metadata={
                        'type': 'shortcut',
                        'shortcut_name': shortcut_info['name'],
                        'shortcut_data': shortcut_info['data'],
                        'score': shortcut_info['score'],
                        'status': request.status.value
                    },
                    score=shortcut_info['score']
                )
                memories.append(memory_item)

            memories.sort(key=lambda x: x.score or 0, reverse=True)

            return MemoryResponse(
                memories=memories,
                memory_type=self.memory_type,
                total_count=len(memories),
                request_id=str(uuid.uuid4())
            )

        except Exception as e:
            print(f"Error providing MobileE memory: {e}")
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0
            )

    
    def _format_tip_content(self, tip: str, status: MemoryStatus) -> str:
        try:
            if status == MemoryStatus.BEGIN:
                return f"MobileE Tip: {tip}"
            elif status == MemoryStatus.IN:
                return None 
            
            return f"MobileE Tip: {tip}"
            
        except Exception:
            return f"MobileE Tip: {tip}"
    
    def _format_shortcut_content(self, name: str, data: Dict, status: MemoryStatus) -> str:
        try:
            description = data.get('description', '')
            
            if status == MemoryStatus.BEGIN:
                return f"MobileE Available Approach: {name}\n{description}"
            elif status == MemoryStatus.IN:
                return None 
            
            return f"MobileE Shortcut: {name}: {description}"
            
        except Exception:
            return f"MobileE Shortcut: {name}: {data.get('description', '')}"
    
    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        try:
            absorbed_memory = ""

            new_tips = self._extract_tips_with_llm(trajectory_data)
            if new_tips:
                self._append_tips(new_tips)
                absorbed_memory += f"Extracted tips: {new_tips}"

            is_success = False
            if trajectory_data.metadata and isinstance(trajectory_data.metadata, dict):
                is_success = bool(trajectory_data.metadata.get("is_correct", False))

            if is_success:
                new_shortcuts = self._extract_shortcuts_with_llm(trajectory_data)
                if new_shortcuts:
                    self._append_shortcuts(new_shortcuts)
                    absorbed_memory += f" | Extracted shortcuts: {new_shortcuts}"

            return True, absorbed_memory

        except Exception as e:
            error_msg = f"Error taking in MobileE memory: {e}"
            print(error_msg)
            return False, error_msg
    
    def _extract_tips_with_llm(self, trajectory_data: TrajectoryData) -> List[str]:
        if self.model is None:
            print("Warning: No LLM model available for tip extraction")
            return []
        
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)
            
            is_success = False
            if trajectory_data.metadata and isinstance(trajectory_data.metadata, dict):
                is_success = bool(trajectory_data.metadata.get("is_correct", False))
            
            outcome_context = "successful" if is_success else "failed"
            
            prompt = f"""Analyze the following {outcome_context} task execution and extract actionable tips for future similar tasks.

Task Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "No result provided"}

Please extract 3-5 concise, actionable tips that would be valuable for similar future tasks:
- For successful trajectories: Focus on effective strategies, best practices, and key success factors
- For failed trajectories: Focus on what to avoid, common pitfalls, and preventive measures

Requirements:
- Each tip should be 1-2 sentences maximum
- Tips should be practical and immediately actionable
- Focus on reusable knowledge that applies to similar task types
- Return only the tips, one per line, no additional text"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            
            tips = []
            for line in content.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and len(line) > 10: 
                    cleaned_line = line.lstrip('•-*123456789. ')
                    if cleaned_line:
                        tips.append(cleaned_line)
            
            return tips[:5] 
            
        except Exception as e:
            print(f"Error extracting tips with LLM: {e}")
            return []

    def _extract_shortcuts_with_llm(self, trajectory_data: TrajectoryData) -> Dict[str, Dict]:
        if self.model is None:
            print("Warning: No LLM model available for shortcut extraction")
            return {}
        
        try:
            trajectory_text = self._format_trajectory_for_model(trajectory_data)
            
            prompt = f"""Analyze the following successful task execution and create a reusable action sequence (shortcut) for similar tasks.

Task Question: {trajectory_data.query}

Successful Execution Trajectory:
{trajectory_text}

Task Result: {trajectory_data.result if trajectory_data.result else "No result provided"}

Please create a structured shortcut that captures the successful approach:

1. Name: A concise name for this approach (e.g., "web_search_and_verify")
2. Description: Brief description of what this shortcut accomplishes
3. Precondition: When this shortcut should be used
4. Action Sequence: 3-6 key steps that capture the essential actions

Format your response as JSON:
{{
    "name": "shortcut_name",
    "description": "Brief description of the approach",
    "precondition": "When to use this shortcut",
    "atomic_action_sequence": [
        {{"name": "step1", "arguments_map": {{"task": "description of step 1"}}}},
        {{"name": "step2", "arguments_map": {{"task": "description of step 2"}}}},
        ...
    ]
}}

Return only the JSON, no additional text."""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
            
            response = self.model(messages)
            content = getattr(response, "content", str(response))
            
            try:
                if content.startswith('```json'):
                    content = content[7:-3].strip()
                elif content.startswith('```'):
                    content = content[3:-3].strip()
                
                shortcut_data = json.loads(content)
                
                if all(key in shortcut_data for key in ["name", "description", "atomic_action_sequence"]):
                    shortcut_name = shortcut_data["name"]
                    return {shortcut_name: shortcut_data}
                else:
                    print("Invalid shortcut data structure from LLM")
                    return {}
                    
            except json.JSONDecodeError as e:
                print(f"Error parsing shortcut JSON: {e}")
                return {}
            
        except Exception as e:
            print(f"Error extracting shortcuts with LLM: {e}")
            return {}



    def _format_trajectory_for_model(self, trajectory_data: TrajectoryData) -> str:
        trajectory_parts = []
        for i, step in enumerate(trajectory_data.trajectory):
            step_type = step.get("type", "step")
            content = str(step.get("content", "")).strip()
            if content:
                trajectory_parts.append(f"Step {i+1} [{step_type}]: {content}")
        return "\n".join(trajectory_parts) if trajectory_parts else "No trajectory steps recorded"

    def _append_tips(self, new_tips: List[str]):
        try:
            current_tips = []
            if os.path.exists(self.tips_file_path):
                with open(self.tips_file_path, 'r', encoding='utf-8') as f:
                    tips_data = json.load(f)
                    current_tips = tips_data.get('tips', [])
            
            for tip in new_tips:
                if tip not in current_tips:
                    current_tips.append(tip)
            
            tips_data = {"tips": current_tips}
            os.makedirs(os.path.dirname(self.tips_file_path), exist_ok=True)
            with open(self.tips_file_path, 'w', encoding='utf-8') as f:
                json.dump(tips_data, f, indent=2, ensure_ascii=False)
            
            self.tips = current_tips
            
        except Exception as e:
            print(f"Error appending tips: {e}")

    def _append_shortcuts(self, new_shortcuts: Dict[str, Dict]):
        try:
            current_shortcuts = {}
            if os.path.exists(self.shortcuts_file_path):
                with open(self.shortcuts_file_path, 'r', encoding='utf-8') as f:
                    current_shortcuts = json.load(f)
            
            current_shortcuts.update(new_shortcuts)
            
            os.makedirs(os.path.dirname(self.shortcuts_file_path), exist_ok=True)
            with open(self.shortcuts_file_path, 'w', encoding='utf-8') as f:
                json.dump(current_shortcuts, f, indent=2, ensure_ascii=False)
            
            self.shortcuts = current_shortcuts
            
        except Exception as e:
            print(f"Error appending shortcuts: {e}")