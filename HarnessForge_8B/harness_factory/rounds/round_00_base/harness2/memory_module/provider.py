import json
import os
import uuid
from typing import List, Optional, Dict, Any
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None
from module_memory.providers.model_loader import load_sentence_transformer

from module_memory.base_memory import BaseMemoryProvider, atomic_write_json, file_lock
from module_memory.memory_types import (
    MemoryRequest, 
    MemoryResponse, 
    TrajectoryData, 
    MemoryType, 
    MemoryItem,
    MemoryStatus
)

def load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                         cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    return load_sentence_transformer(
        model_name=model_name,
        cache_dir=cache_dir,
        allow_unavailable=SentenceTransformer is None,
    )


@dataclass
class WorkflowInstance:
    workflow_id: str = field(default_factory=lambda: str(datetime.now().timestamp()))
    query: str = ""
    agent_planning: Optional[str] = None
    search_agent_planning: Optional[str] = None
    agent_experience: Optional[str] = None
    search_agent_experience: Optional[str] = None
    query_embedding: Optional[np.ndarray] = None
    plan_embedding: Optional[np.ndarray] = None
    search_plan_embedding: Optional[np.ndarray] = None


class AgenticKnowledgeBase:

    def __init__(self, json_file_paths=None, model_cache_dir: str = './storage/models'):
        self.workflows: Dict[str, WorkflowInstance] = {}
        self.embedding_model = load_embedding_model(
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            cache_dir=model_cache_dir
        )
        
        self.field_components = {
            'query': {
                'vectorizer': TfidfVectorizer(stop_words='english'),
                'matrix': None,
                'workflow_ids': []
            },
        }
        
        if json_file_paths:
            self.load_initial_data(json_file_paths)
            self.finalize_index()

    def load_initial_data(self, json_file_paths):
        for json_path in json_file_paths:
            if not os.path.exists(json_path):
                raise FileNotFoundError(f'JSON file not found: {json_path}')
            self.parse_json_file(json_path)

    def _load_json_with_fallback(self, json_file_path: str):
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(json_file_path, "r", encoding=encoding) as f:
                    return json.load(f)
            except UnicodeDecodeError:
                continue
        with open(json_file_path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)

    def parse_json_file(self, json_file_path):
        try:
            data = self._load_json_with_fallback(json_file_path)
            batch = []
            for item in data:
                try:
                    instance = WorkflowInstance(
                        query = item.get('question', ''),
                        agent_planning = item.get('agent_planning'),
                        search_agent_planning = item.get('search_agent_planning'),
                        agent_experience = item.get('agent_experience'),
                        search_agent_experience = item.get('search_agent_experience')
                    )
                    batch.append(instance)
                except KeyError as e:
                    continue
            for instance in batch:
                self.workflows[instance.workflow_id] = instance
        except Exception as e:
            print(f"Error parsing file: {json_file_path} | {e}")

    def add_workflow_instance(self, workflow: WorkflowInstance):
        self.workflows[workflow.workflow_id] = workflow
        return workflow

    def finalize_index(self):
        self.build_tfidf_indices()
        self.build_embeddings()

    def build_tfidf_indices(self):
        field_data = {
            'query': [],
        }
        
        for workflow in self.workflows.values():
            field_data['query'].append(workflow.query)
        
        for field in ['query']:
            if len(field_data[field]) == 0:
                continue
                
            vectorizer = self.field_components[field]['vectorizer']
            self.field_components[field]['matrix'] = vectorizer.fit_transform(field_data[field])
            self.field_components[field]['workflow_ids'] = list(self.workflows.keys())

    def build_embeddings(self):
        if self.embedding_model is None:
            for workflow in self.workflows.values():
                workflow.query_embedding = None
            return

        workflows = list(self.workflows.values())
        batch_size = 32
        
        queries = [w.query for w in workflows]
        query_embeddings = self.embedding_model.encode(
            queries, 
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        for i, workflow in enumerate(workflows):
            workflow.query_embedding = query_embeddings[i]

    def field_text_search(self, query: str, field: str, top_k: int = 3) -> List[dict]:
        component = self.field_components[field]
        if component['matrix'] is None or not component['workflow_ids']:
            return []
        
        query_vec = component['vectorizer'].transform([query])
        similarities = cosine_similarity(query_vec, component['matrix']).flatten()
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        return [{
            'workflow_id': component['workflow_ids'][idx],
            'score': float(similarities[idx]),
            'field': field,
            'content': getattr(self.workflows[component['workflow_ids'][idx]], 
                             field if field != 'search_plan' else 'search_agent_planning')
        } for idx in top_indices]

    def field_semantic_search(self, query: str, field: str, top_k: int = 3) -> List[dict]:
        if self.embedding_model is None:
            return []

        query_embedding = self.embedding_model.encode(query, convert_to_numpy=True)

        embedding_field_map = {
            'query': 'query_embedding',
        }
        
        content_field_map = {
            'query': 'query',
        }
        
        embeddings = []
        workflows = []
        for wf_id, workflow in self.workflows.items():
            emb = getattr(workflow, embedding_field_map[field], None)
            if emb is not None:
                embeddings.append(emb)
                workflows.append(workflow)
        
        if not embeddings:
            return []
        
        similarities = cosine_similarity([query_embedding], embeddings)[0]
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        return [{
            'workflow_id': workflows[idx].workflow_id,
            'score': float(similarities[idx]),
            'field': field,
            'content': getattr(workflows[idx], content_field_map[field], "")
        } for idx in top_indices]


class AKB_Manager:

    def __init__(self, json_file_paths=None, model_cache_dir: str = './storage/models'):
        self.knowledge_base = AgenticKnowledgeBase(
            json_file_paths=json_file_paths,
            model_cache_dir=model_cache_dir
        )
    
    def hybrid_search(self, query: str, top_k: int = 5, 
                      weights: Dict[str, float] = None) -> List[dict]:
        weights = weights or {'text': 0.5, 'semantic': 0.5}
        field_weights = {'query': 1.0}
        
        score_board = defaultdict(float)
        
        for field in ['query']:
            for result in self.knowledge_base.field_text_search(query, field, top_k*2):
                score_board[result['workflow_id']] += weights['text'] * field_weights[field] * result['score']
            for result in self.knowledge_base.field_semantic_search(query, field, top_k*2):
                score_board[result['workflow_id']] += weights['semantic'] * field_weights[field] * result['score']
        
        sorted_results = sorted(score_board.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        detailed_results = []
        for wf_id, total_score in sorted_results:
            workflow = self.knowledge_base.workflows[wf_id]
            detailed_results.append({
                'workflow_id': wf_id,
                'total_score': total_score,
                'query': workflow.query,
                'plan': workflow.agent_planning,
                'search_plan': workflow.search_agent_planning,
                'agent_experience': workflow.agent_experience,
                'search_agent_experience': workflow.search_agent_experience
            })
        
        return detailed_results
    
    def search_by_text(self, query: str, field: str = "query", top_k: int = 3) -> List[dict]:
        results = []
        for result in self.knowledge_base.field_text_search(query, field, top_k):
            workflow = self.get_workflow_details(result['workflow_id'])
            results.append({
                'workflow_id': result['workflow_id'],
                'score': result['score'],
                'content': {
                    'query': workflow.query,
                    'plan': workflow.agent_planning,
                    'search_plan': workflow.search_agent_planning,
                    'agent_experience': workflow.agent_experience,
                    'search_agent_experience': workflow.search_agent_experience
                }
            })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]
    
    def search_by_semantic(self, query: str, field: str = "query", top_k: int = 3) -> List[dict]:
        results = []
        for result in self.knowledge_base.field_semantic_search(query, field, top_k):
            workflow = self.get_workflow_details(result['workflow_id'])
            results.append({
                'workflow_id': result['workflow_id'],
                'score': result['score'],
                'content': {
                    'query': workflow.query,
                    'plan': workflow.agent_planning,
                    'search_plan': workflow.search_agent_planning,
                    'agent_experience': workflow.agent_experience,
                    'search_agent_experience': workflow.search_agent_experience
                }
            })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]

    def get_workflow_details(self, workflow_id: str) -> Optional[WorkflowInstance]:
        return self.knowledge_base.workflows.get(workflow_id)


class MemoryProvider(BaseMemoryProvider):
    
    DEFAULT_PROMPTS = {
        'student_agent_reason': """Extract key information from user query to construct efficient search terms for retrieving the most relevant results.

Requirements:
1. Analyze the user's question to identify core concepts, terminology, and keywords
2. Extract contextual information and constraints that may impact search quality
3. Break down complex questions into searchable components
4. Identify the domain, subject matter, and specific needs of the question

Output format:
<core concepts or topics of the question>

Ensure search terms are specific enough to retrieve relevant information while maintaining sufficient breadth to capture related cases.
Combine technical terminology with everyday expressions to optimize search effectiveness.

Here is the user query:
{{user_query}}"""
    }
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(MemoryType.AGENT_KB, config)

        self.kb_database_path = self.config.get(
            "kb_database_path",
            "./storage/agent_kb/agent_kb_database.json"
        )
        self.top_k = self.config.get("top_k", 3)
        self.search_weights = self.config.get(
            "search_weights",
            {'text': 0.5, 'semantic': 0.5}
        )

        self.model_cache_dir = self.config.get(
            "model_cache_dir",
            "./storage/models"
        )

        self.model = self.config.get("model", None)
        self.akb_manager: Optional[AKB_Manager] = None
    
    def initialize(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.kb_database_path), exist_ok=True)
            
            if not os.path.exists(self.kb_database_path):
                atomic_write_json(self.kb_database_path, [], indent=2)
            
            self.akb_manager = AKB_Manager(
                json_file_paths=[self.kb_database_path],
                model_cache_dir=self.model_cache_dir
            )
            return True
            
        except Exception as e:
            print(f"Error initializing Agent KB provider: {e}")
            return False

    def _reason_for_retrieval(self, request: MemoryRequest) -> str:
        if not self.model:
            return request.query
        
        reason_prompt = self.DEFAULT_PROMPTS['student_agent_reason']
        prompt = reason_prompt.replace('{{user_query}}', request.query)
        
        try:
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
            refined_query = getattr(response, "content", str(response)).strip()
            
            return refined_query if refined_query else request.query
            
        except Exception as e:
            print(f"Error in reasoning step: {e}")
            return request.query
    
    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        if not self.akb_manager:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        if request.status != MemoryStatus.BEGIN:
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

        try:
            refined_query = self._reason_for_retrieval(request)
            
            search_results = self.akb_manager.hybrid_search(
                query=refined_query,
                top_k=self.top_k,
                weights=self.search_weights
            )
            
            if not search_results:
                return MemoryResponse(
                    memories=[],
                    memory_type=self.memory_type,
                    total_count=0,
                    request_id=str(uuid.uuid4())
                )
            
            synthesized_content = self._synthesize_all_memories(search_results, request)
            
            memory_item = MemoryItem(
                id=f"synthesized_{uuid.uuid4()}",
                content=synthesized_content,
                metadata={
                    'num_sources': len(search_results),
                    'source_queries': [r['query'] for r in search_results],
                    'avg_score': sum(r['total_score'] for r in search_results) / len(search_results),
                    'status': request.status.value,
                    'original_query': request.query,
                    'refined_query': refined_query
                },
                score=sum(r['total_score'] for r in search_results) / len(search_results)
            )
            
            return MemoryResponse(
                memories=[memory_item],
                memory_type=self.memory_type,
                total_count=1,
                request_id=str(uuid.uuid4())
            )
            
        except Exception as e:
            print(f"Error providing memory: {e}")
            return MemoryResponse(
                memories=[],
                memory_type=self.memory_type,
                total_count=0,
                request_id=str(uuid.uuid4())
            )

    def _synthesize_all_memories(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if request.status == MemoryStatus.BEGIN:
                student_guidance = self._synthesize_student_guidance(results, request)
                teacher_guidance = self._synthesize_teacher_guidance(results, request)

                return (
                    "AGENT-KB Student Guidance:\n"
                    f"{student_guidance}\n\n"
                    "AGENT-KB Teacher Guidance:\n"
                    f"{teacher_guidance}"
                )

            queries = [r['query'] for r in results if r.get('query')]
            return f"AGENT-KB Guidance: {'; '.join(queries)}"

        except Exception as e:
            print(f"Error synthesizing memories: {e}")
            queries = [r.get('query', '') for r in results if r.get('query')]
            joined = '; '.join(queries) if queries else results[0].get('query', '')
            return f"AGENT-KB Guidance: {joined}"

    def _synthesize_student_guidance(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if not self.model:
                all_plans = []
                for r in results:
                    if r.get('plan'):
                        all_plans.append(r['plan'])
                    if r.get('search_plan'):
                        all_plans.append(r['search_plan'])
                return ' '.join(all_plans) if all_plans else results[0].get('query', '')

            all_planning_content = []
            for i, result in enumerate(results, 1):
                source_parts = []
                
                if result.get('query'):
                    source_parts.append(f"Similar task:\n{result['query']}")
                
                suggestions = []
                if result.get('plan'):
                    suggestions.append(result['plan'])
                if result.get('search_plan'):
                    suggestions.append(result['search_plan'])
                
                if suggestions:
                    source_parts.append(f"Suggestions:\n{' '.join(suggestions)}")
                
                if source_parts:
                    all_planning_content.append('\n'.join(source_parts))

            if not all_planning_content:
                return results[0].get('query', '')

            matched_content = "\n\n".join(all_planning_content)
            
            prompt = f"""Analyze similar tasks and past experiences to generate concise, actionable suggestions for improving the current plan. Based on the patterns identified in relevant tasks and insights from the knowledge base, provide specific recommendations.

**Key Requirements:**
1. Focus exclusively on technical/behavioral improvements derived from similar task patterns and experience.
2. Provide root-cause solutions and implementation strategies based on past successes.
3. Provide 2-3 specific suggestions only.
4. Format output strictly as:
   1. [Specific suggestion 1]
   2. [Specific suggestion 2]
   ...
5. Use gentle, suggestive language rather than directive commands.
No headings, explanations, or markdown.

**Current Task:** {request.query}

**You can refer to similar tasks, plans, and corresponding experience to provide your suggestions:**
{matched_content}"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            response = self.model(messages)
            guidance = getattr(response, "content", str(response)).strip()

            return guidance if guidance else '; '.join([r.get('query', '') for r in results])

        except Exception as e:
            print(f"Error synthesizing student guidance: {e}")
            return results[0].get('query', '')

    def _synthesize_teacher_guidance(self, results: List[Dict[str, Any]], request: MemoryRequest) -> str:
        try:
            if not self.model:
                all_experiences = []
                for r in results:
                    if r.get('agent_experience'):
                        all_experiences.append(r['agent_experience'])
                    if r.get('search_agent_experience'):
                        all_experiences.append(r['search_agent_experience'])
                return ' '.join(all_experiences) if all_experiences else results[0].get('query', '')

            all_experience_content = []
            for i, result in enumerate(results, 1):
                source_content = []
                if result.get('query'):
                    source_content.append(f"Query: {result['query']}")
                if result.get('agent_experience'):
                    source_content.append(f"Agent Experience: {result['agent_experience']}")
                if result.get('search_agent_experience'):
                    source_content.append(f"Search Experience: {result['search_agent_experience']}")
                
                if source_content:
                    all_experience_content.append(
                        f"Source {i} (Score: {result.get('total_score', 0):.3f}):\n" +
                        "\n".join(source_content)
                    )

            if not all_experience_content:
                return results[0].get('query', '')

            agent_context = ""
            if request and request.context:
                max_context_length = 1000
                truncated_context = request.context
                if len(request.context) > max_context_length:
                    truncated_context = "... [truncated]\n" + request.context[-max_context_length:]
                agent_context = f"\n\nCurrent Agent Context:\n{truncated_context}"

            matched_content = "\n\n".join(all_experience_content)
            
            prompt = f"""You are an experienced AI agent teacher synthesizing multiple experience entries to provide unified operational guidance.

Current Task: {request.query}

Retrieved Experience Entries ({len(results)} sources):
{matched_content}{agent_context}

Based on ALL the matched experience above, synthesize cohesive, unified operational guidance for the agent. Your guidance should:

1. Integrate techniques and methods from all sources
2. Combine common pitfalls and best practices across sources
3. Provide specific, actionable execution tips

Requirements:
- Be specific and comprehensive (2-3 sentences)
- Focus on detailed operations and practical techniques
- Present a unified perspective synthesizing all sources
- Provide concrete, actionable suggestions
- Help refine and improve the current approach based on collective experience
- Use gentle, suggestive language rather than directive commands.
Provide only the synthesized guidance text with no additional explanations or source references."""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            response = self.model(messages)
            guidance = getattr(response, "content", str(response)).strip()

            return guidance if guidance else '; '.join([r.get('query', '') for r in results])

        except Exception as e:
            print(f"Error synthesizing teacher guidance: {e}")
            return results[0].get('query', '')



    def take_in_memory(self, trajectory_data: TrajectoryData) -> tuple[bool, str]:
        """
        Ingest new memory by intelligently summarizing trajectory with model
        Only processes successful task executions
        """
        try:
            if not self.model:
                error_msg = "Error: No model provided for memory summarization"
                print(error_msg)
                return False, error_msg

            # Check if task was successful before processing
            if not self._is_task_successful(trajectory_data):
                msg = "Skipping memory ingestion: Task was not successful"
                print(msg)
                return False, msg

            # Use model to intelligently summarize the trajectory
            memory_summary = self._summarize_trajectory_with_model(trajectory_data)

            if not memory_summary:
                error_msg = "Error: Model summarization failed"
                print(error_msg)
                return False, error_msg
            
            # Create new workflow instance data with model-generated summaries
            new_workflow = {
                "question": trajectory_data.query,
                "agent_planning": memory_summary.get("agent_planning", ""),
                "search_agent_planning": memory_summary.get("search_agent_planning", ""),
                "agent_experience": memory_summary.get("agent_experience", ""),
                "search_agent_experience": memory_summary.get("search_agent_experience", ""),
                "timestamp": datetime.now().isoformat(),
                "metadata": trajectory_data.metadata or {}
            }
            
            # Append to database file (ensure dir)
            os.makedirs(os.path.dirname(self.kb_database_path), exist_ok=True)
            with file_lock(self.kb_database_path):
                if os.path.exists(self.kb_database_path):
                    try:
                        with open(self.kb_database_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except Exception:
                        data = []
                else:
                    data = []

                if not isinstance(data, list):
                    data = []

                data.append(new_workflow)
                atomic_write_json(self.kb_database_path, data, indent=2)
            
            # Reinitialize the manager to include new data
            self.akb_manager = AKB_Manager(json_file_paths=[self.kb_database_path])

            absorbed_memory = f"Summarized trajectory: {memory_summary}"
            return True, absorbed_memory

        except Exception as e:
            error_msg = f"Error taking in memory: {e}"
            print(error_msg)
            return False, error_msg

    def _is_task_successful(self, trajectory_data: TrajectoryData) -> bool:
        try:
            metadata = trajectory_data.metadata or {}
            
            if 'is_correct' in metadata:
                return metadata['is_correct'] is True
            
            if 'success' in metadata:
                return metadata['success'] is True
            if 'task_success' in metadata:
                return metadata['task_success'] is True
            
            return False
            
        except Exception as e:
            print(f"Error determining task success: {e}")
            return False

    def _format_trajectory_for_model(self, trajectory_data: TrajectoryData) -> str:
        if not trajectory_data.trajectory:
            return "No execution trajectory available"
            
        trajectory_parts = []
        trajectory_parts.append(f"Task: {trajectory_data.query}")
        trajectory_parts.append("")
        
        for i, step in enumerate(trajectory_data.trajectory, 1):
            step_type = step.get('type', 'step')
            content = step.get('content', '')
            trajectory_parts.append(f"Step {i} ({step_type}): {content}")
        
        if trajectory_data.result:
            trajectory_parts.append("")
            trajectory_parts.append(f"Final Result: {trajectory_data.result}")
        
        return "\n".join(trajectory_parts)

    def _summarize_trajectory_with_model(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, str]]:
        """
        Use model to intelligently summarize the trajectory into structured memory components
        """
        try:
            # Prepare trajectory content for model
            trajectory_text = self._format_trajectory_for_model(trajectory_data)
            
            # Create enhanced summarization prompt based on high-quality examples
            prompt = f"""You are an expert AI agent trainer analyzing a successful task execution to extract high-quality memory patterns for future similar tasks.

TASK ANALYSIS:
Question: {trajectory_data.query}

Execution Trajectory:
{trajectory_text}

Final Result: {trajectory_data.result if trajectory_data.result else "Task completed successfully"}

MEMORY EXTRACTION INSTRUCTIONS:
Extract structured memory components that capture the strategic thinking and methodological approaches used in this successful execution. Focus on actionable insights, specific techniques, and reusable patterns.

Please provide detailed analysis in the following JSON format:

{{
    "agent_planning": "Detailed strategic planning approach with numbered steps, decision-making criteria, tool selection rationale, and problem decomposition strategy",
    "search_agent_planning": "Comprehensive search strategy including query formulation techniques, source prioritization methods, information extraction approaches, and result validation processes", 
    "agent_experience": "Key lessons learned, successful methodologies, best practices discovered, error avoidance strategies, and general principles that can guide future similar tasks",
    "search_agent_experience": "Search-specific insights including effective query patterns, reliable source types, information validation techniques, and data processing approaches"
}}

QUALITY REQUIREMENTS:
1. Each field must contain substantial, specific content (minimum 2-3 detailed sentences)
2. Focus on ACTIONABLE strategies and CONCRETE methodologies, not generic descriptions
3. Include specific decision points, tool choices, and reasoning patterns
4. Emphasize successful techniques that led to task completion
5. Extract transferable knowledge that applies to similar problem types
6. Use professional, instructional language as if training another agent
7. Include specific examples or patterns where applicable

EXAMPLES OF HIGH-QUALITY CONTENT:
- Agent Planning: "1. Decompose the inquiry: Identify entities using biographical clues... 2. Data/Tool Use Decisions: Use search to resolve identity and find detailed biography... 3. Delegation Strategy: Author identification requires multi-clue queries..."
- Search Experience: "Construct layered queries that combine multiple discriminators (facts, dates, roles) to improve specificity... Select sources with documented editorial oversight..."

Return ONLY the JSON object with no additional text or explanations."""

            # Call model for summarization using proper message format
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
            
            try:
                response = self.model(messages)
                response_text = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                print(f"Error calling model: {e}")
                return None
            
            # Extract JSON from response
            try:
                # Try to find JSON in response
                import re
                
                # First try to parse the entire response as JSON
                try:
                    memory_summary = json.loads(response_text.strip())
                except json.JSONDecodeError:
                    # If that fails, try to extract JSON block
                    json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        memory_summary = json.loads(json_str)
                    else:
                        print(f"Warning: No JSON found in model response: {response_text[:500]}...")
                        return None
                
                # Validate required fields and content quality
                required_fields = ["agent_planning", "search_agent_planning", "agent_experience", "search_agent_experience"]
                if all(field in memory_summary and memory_summary[field].strip() for field in required_fields):
                    # Additional quality check - ensure substantial content
                    if all(len(memory_summary[field].strip()) >= 50 for field in required_fields):
                        print(f"Successfully extracted high-quality memory summary")
                        return memory_summary
                    else:
                        print(f"Warning: Memory content too brief, requires more detailed analysis")
                        return None
                else:
                    print(f"Warning: Missing or empty required fields in model response: {list(memory_summary.keys())}")
                    return None
                    
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse JSON from model response: {e}")
                print(f"Response text: {response_text[:500]}...")
                return None
            
        except Exception as e:
            print(f"Error in model summarization: {e}")
            return None


AgentKBProvider = MemoryProvider
MEMORY_SYSTEM = MemoryType.AGENT_KB.value

__all__ = ["MEMORY_SYSTEM", "MemoryProvider", "AgentKBProvider"]
