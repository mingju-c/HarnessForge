"""
Cerebra Fusion Memory Provider

through a graph-backed architecture with intelligent routing and continuous optimization.

"""

import os
import json
import uuid
import re
import ast
import hashlib
import importlib.util
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from datetime import datetime
from collections import defaultdict
from enum import Enum

import numpy as np

# Vectorization and semantic models
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

# Unified memory base imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
from ..base_memory import BaseMemoryProvider
from ..memory_types import (
    MemoryRequest,
    MemoryResponse,
    MemoryItem,
    MemoryItemType,
    TrajectoryData,
    MemoryStatus,
    MemoryType
)

# Tool wrapper for API memory
try:
    from storage.tools.tool_wrapper import ToolWrapper
except ImportError:
    ToolWrapper = None


# =========================================================================
# Utility Functions
# =========================================================================

def _safe_get_model_response(model, prompt: str) -> Optional[str]:
    """Robust LLM invocation helper returning string content or None."""
    if model is None:
        return None
    
    try:
        # Minimal compatibility with smolagents or OpenAI-style clients
        try:
            from smolagents.models import MessageRole
            messages = [{"role": MessageRole.USER, "content": [{"type": "text", "text": prompt}]}]
            resp = model(messages)
            result = getattr(resp, "content", str(resp)).strip()
            return result
        except Exception:
            # Fallback: direct call style
            resp = model(prompt)
            result = str(resp).strip()
            return result
    except Exception:
        return None


def _load_embedding_model(model_name: str = 'sentence-transformers/all-MiniLM-L6-v2',
                          cache_dir: str = './storage/models') -> Optional[SentenceTransformer]:
    """Load embedding model with local cache fallback; returns None if unavailable."""
    if SentenceTransformer is None:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    local_model_path = os.path.join(cache_dir, model_name.replace('/', '_'))
    try:
        if os.path.exists(local_model_path) and os.listdir(local_model_path):
            model = SentenceTransformer(local_model_path)
            return model
    except Exception:
        pass
    try:
        model = SentenceTransformer(model_name)
        try:
            model.save(local_model_path)
        except Exception:
            pass
        return model
    except Exception:
        return None


# =========================================================================
# Graph Components
# =========================================================================

class EdgeType(Enum):
    """Types of edges in the memory graph."""
    SAME_TASK = "same_task"          # Nodes from same task execution
    SIMILAR_CONCEPT = "similar"       # Semantically similar content
    DEPENDS_ON = "depends"            # Dependency relationship
    COOCCURS = "cooccurs"             # Frequently retrieved together


@dataclass
class NexusEdge:
    """Graph edge with type and weight for dynamic optimization."""
    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    usage_count: int = 0
    success_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize edge to dictionary."""
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'NexusEdge':
        """Deserialize edge from dictionary."""
        return NexusEdge(
            source=data["source"],
            target=data["target"],
            edge_type=EdgeType(data["edge_type"]),
            weight=data.get("weight", 1.0),
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


@dataclass
class NexusNode:
    """Graph node representing a memory unit."""
    id: str
    node_type: str  # "task", "pattern", "playbook", "checklist", "failure", "success"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    signature: str = ""  # Content hash for deduplication


@dataclass
class GraphIndex:
    """Multi-granularity indices for nodes."""
    tfidf_vectorizer: Optional[TfidfVectorizer] = None
    tfidf_matrix: Optional[Any] = None
    node_ids: List[str] = field(default_factory=list)
    embeddings: Optional[np.ndarray] = None


# =========================================================================
# Tool Components
# =========================================================================

@dataclass
class ToolRecord:
    """Metadata for a stored tool."""
    name: str
    description: str
    code: str
    domain: str = "general"
    tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    success_count: int = 0
    signature: str = ""


# =========================================================================
# Main Provider
# =========================================================================

class CerebraFusionMemoryProvider(BaseMemoryProvider):
    """
    Cerebra Fusion Memory Provider: Unified Text + Tool Memory System
    
    Configuration:
    - enable_tool_memory: bool (default: True) - Enable tool memory path
    - consolidation_interval: int (default: 50) - Tasks between consolidations
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(self._get_declared_memory_type(), config or {})
        
        # Core configuration
        self.storage_dir = self.config.get("storage_dir", "./storage/cerebra_fusion")
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.db_path = self.config.get("db_path", os.path.join(self.storage_dir, "cf_database.json"))
        self.model_cache_dir = self.config.get("model_cache_dir", "./storage/models")
        
        # Text memory configuration
        self.top_k = int(self.config.get("top_k", 5))
        self.search_weights = self.config.get("search_weights", {"text": 0.2, "semantic": 0.8})
        self.min_score = float(self.config.get("min_score", 0.22))
        self.min_score_in_phase = float(self.config.get("min_score_in_phase", 0.22))
        
        # Graph configuration
        self.semantic_edge_threshold = float(self.config.get("semantic_edge_threshold", 0.75))
        self.max_neighbors_expand = int(self.config.get("max_neighbors_expand", 3))
        self.enable_graph_expansion = bool(self.config.get("enable_graph_expansion", True))
        
        # Tool memory configuration (new)
        self.enable_tool_memory = bool(self.config.get("enable_tool_memory", True))
        self.tools_storage_path = self.config.get("tools_storage_path", 
                                                   os.path.join(self.storage_dir, "tools_storage.py"))
        self.max_tool_candidates = int(self.config.get("max_tool_candidates", 3))
        
        # Consolidation configuration
        self.consolidation_interval = int(self.config.get("consolidation_interval", 50))
        self.task_counter = 0
        
        # Models
        self.embedding_model = _load_embedding_model(cache_dir=self.model_cache_dir)
        self.model = self.config.get("model", None)

        # Graph store
        self.nodes: Dict[str, NexusNode] = {}
        self.edges: List[NexusEdge] = []
        
        # Tool store
        self.tools: Dict[str, ToolRecord] = {}
        self.tools_registry: Dict[str, Callable] = {}
        self.tool_wrapper = None
        if self.enable_tool_memory and ToolWrapper:
            self.tool_wrapper = ToolWrapper(model=self.model, logger=None)
        
        # Indices
        self.text_index = GraphIndex(tfidf_vectorizer=TfidfVectorizer(stop_words='english'))
        self.tool_embeddings: Optional[np.ndarray] = None
        self.tool_names_index: List[str] = []
        
        # Track memory usage for success rate calculation
        # Maps request_id -> {"node_ids": [...], "edge_pairs": [(source, target), ...]}
        self.active_usage_tracking: Dict[str, Dict[str, Any]] = {}

        # Initialize storage
        self._load_or_initialize_db()
        self._finalize_indices()

    def initialize(self) -> bool:
        """Initialize the memory provider."""
        try:
            if not self.nodes:
                self._seed_core_patterns()
                self._persist_db()
            if not self.text_index.node_ids:
                self._finalize_indices()
            if self.enable_tool_memory:
                self._load_tools()
            return True
        except Exception as e:
            print(f"Failed to initialize CerebraFusionMemoryProvider: {e}")
            return False

    @staticmethod
    def _get_declared_memory_type():
        """Get memory type enum."""
        try:
            return MemoryType.CEREBRA_FUSION_MEMORY
        except Exception:
            class _ShimEnum:
                CEREBRA_FUSION_MEMORY = "cerebra_fusion_memory"
            return _ShimEnum.CEREBRA_FUSION_MEMORY

    # =========================================================================
    # Text Memory Path
    # =========================================================================

    def _load_or_initialize_db(self):
        """Load existing graph database or initialize with seed patterns."""
        if not os.path.exists(self.db_path):
            self._seed_core_patterns()
            self._persist_db()
            return
        
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Load nodes
            for n in data.get("nodes", []):
                node = NexusNode(
                    id=n["id"],
                    node_type=n["node_type"],
                    content=n["content"],
                    metadata=n.get("metadata", {}),
                    created_at=n.get("created_at", datetime.now().isoformat()),
                    signature=n.get("signature", "")
                )
                self.nodes[node.id] = node
            
            # Load edges
            for e in data.get("edges", []):
                self.edges.append(NexusEdge.from_dict(e))
            
            # Load tools if enabled
            if self.enable_tool_memory:
                for t in data.get("tools", []):
                    tool = ToolRecord(
                        name=t["name"],
                        description=t["description"],
                        code=t["code"],
                        domain=t.get("domain", "general"),
                        tags=t.get("tags", []),
                        usage_count=t.get("usage_count", 0),
                        success_count=t.get("success_count", 0),
                        signature=t.get("signature", "")
                    )
                    self.tools[tool.name] = tool
            
            print(f"[CEREBRA FUSION LOAD] Loaded {len(self.nodes)} nodes, {len(self.edges)} edges, {len(self.tools)} tools")
            
        except Exception as e:
            print(f"[CEREBRA FUSION LOAD] Error loading database: {e}, reinitializing")
            self.nodes.clear()
            self.edges.clear()
            self.tools.clear()
            self._seed_core_patterns()
            self._persist_db()

    def _seed_core_patterns(self):
        """Initialize memory with essential abstract patterns (from Cerebra)."""
        seeds = [
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content="Preserve source phrasing when explicitly requested; avoid over-normalization of reported values.",
                metadata={"category": "format_policy"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content="When progress is incomplete, consider alternate access methods and define clear completion criteria.",
                metadata={"category": "continuation_tactics"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="checklist",
                content="Verify target entity matches question requirements before finalizing answer.",
                metadata={"category": "final_check"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For sports data: use site-restricted search, handle pagination, validate completeness.",
                metadata={"domain": "sports"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For author attribution: check visible byline first; if absent, consider organizational attribution.",
                metadata={"domain": "content_sites"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For archived content: try multiple access paths if one fails.",
                metadata={"domain": "archives"}
            ),
            NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content="For aggregated data: confirm correct entity before extracting details.",
                metadata={"domain": "aggregators"}
            ),
        ]
        for node in seeds:
            node.signature = self._compute_signature(node.content)
            self.nodes[node.id] = node

    def _persist_db(self):
        """Save graph and tools to JSON file."""
        data = {
            "nodes": [vars(n) for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "tools": [vars(t) for t in self.tools.values()] if self.enable_tool_memory else [],
            "metadata": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_tools": len(self.tools),
                "last_updated": datetime.now().isoformat()
            }
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[CEREBRA FUSION PERSIST] Saved {len(self.nodes)} nodes, {len(self.edges)} edges, {len(self.tools)} tools")

    def _finalize_indices(self):
        """Build TF-IDF and semantic embeddings indices for text memory."""
        if not self.nodes:
            return
        
        # Build corpus from node contents
        corpus = [node.content for node in self.nodes.values()]
        self.text_index.node_ids = list(self.nodes.keys())
        
        # Build TF-IDF matrix
        self.text_index.tfidf_matrix = self.text_index.tfidf_vectorizer.fit_transform(corpus)
        
        # Build semantic embeddings if model available
        if self.embedding_model is not None:
            self.text_index.embeddings = self.embedding_model.encode(
                corpus, batch_size=32, convert_to_numpy=True, show_progress_bar=False
            )
            print(f"[CEREBRA FUSION INDEX] Built indices: {len(corpus)} nodes, TF-IDF + embeddings")
        else:
            self.text_index.embeddings = None
            print(f"[CEREBRA FUSION INDEX] Built indices: {len(corpus)} nodes, TF-IDF only")

    def _build_semantic_edges(self, new_node: NexusNode) -> int:
        """Build semantic similarity edges between new node and existing similar nodes."""
        if self.embedding_model is None or self.text_index.embeddings is None or not self.text_index.node_ids:
            return 0
        
        edges_created = 0
        new_embedding = self.embedding_model.encode(new_node.content, convert_to_numpy=True)
        
        for idx, existing_node_id in enumerate(self.text_index.node_ids):
            if existing_node_id == new_node.id:
                continue
            
            existing_node = self.nodes.get(existing_node_id)
            if not existing_node or existing_node.node_type != new_node.node_type:
                continue
            
            # Calculate similarity
            similarity = cosine_similarity([new_embedding], [self.text_index.embeddings[idx]])[0][0]
            
            if similarity >= self.semantic_edge_threshold:
                # Check if edge already exists
                edge_exists = any(
                    (e.source == new_node.id and e.target == existing_node_id) or
                    (e.source == existing_node_id and e.target == new_node.id)
                    for e in self.edges
                )
                
                if not edge_exists:
                    # Create bidirectional edges
                    self.edges.append(NexusEdge(
                        source=new_node.id,
                        target=existing_node_id,
                        edge_type=EdgeType.SIMILAR_CONCEPT,
                        weight=float(similarity),
                        metadata={"similarity_score": float(similarity)}
                    ))
                    self.edges.append(NexusEdge(
                        source=existing_node_id,
                        target=new_node.id,
                        edge_type=EdgeType.SIMILAR_CONCEPT,
                        weight=float(similarity),
                        metadata={"similarity_score": float(similarity)}
                    ))
                    edges_created += 2
        
        if edges_created > 0:
            print(f"[CEREBRA FUSION GRAPH] Created {edges_created} semantic edges for {new_node.node_type}")
        return edges_created

    def _get_neighbors(self, node_id: str, edge_types: Optional[List[EdgeType]] = None) -> List[Tuple[str, float]]:
        """Get neighbors of a node, optionally filtered by edge type."""
        neighbors = []
        for edge in self.edges:
            if edge.source == node_id:
                if edge_types is None or edge.edge_type in edge_types:
                    neighbors.append((edge.target, edge.weight))
        return neighbors

    def _graph_expand(self, initial_results: List[Tuple[str, float]], query: str) -> Tuple[List[Tuple[str, float]], List[Tuple[str, str]]]:
        """Expand retrieval results by adding semantically connected neighbors.
        
        Returns:
            Tuple of (expanded_results, edges_used)
            - expanded_results: List of (node_id, score) pairs
            - edges_used: List of (source_id, target_id) pairs used in expansion
        """
        if not self.enable_graph_expansion or not initial_results:
            return initial_results, []
        
        candidates = {node_id: score for node_id, score in initial_results}
        edges_used = []
        
        for node_id, base_score in initial_results:
            neighbors = self._get_neighbors(node_id, edge_types=[EdgeType.SIMILAR_CONCEPT])
            sorted_neighbors = sorted(neighbors, key=lambda x: x[1], reverse=True)[:self.max_neighbors_expand]
            
            for neighbor_id, edge_weight in sorted_neighbors:
                if neighbor_id not in self.nodes:
                    continue
                
                propagated_score = base_score * edge_weight * 0.7
                candidates[neighbor_id] = max(candidates.get(neighbor_id, 0), propagated_score)
                edges_used.append((node_id, neighbor_id))
        
        # Track edge usage
        for source, target in edges_used:
            for edge in self.edges:
                if edge.source == source and edge.target == target:
                    edge.usage_count += 1
        
        expanded_results = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        
        if len(expanded_results) > len(initial_results):
            print(f"[CEREBRA FUSION GRAPH] Expanded from {len(initial_results)} to {len(expanded_results)} candidates")
        
        return expanded_results, edges_used

    def _hybrid_search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Hybrid search combining TF-IDF and semantic embeddings."""
        scores = defaultdict(float)
        
        # TF-IDF search
        if self.text_index.tfidf_matrix is not None and self.text_index.node_ids:
            q_vec = self.text_index.tfidf_vectorizer.transform([query])
            tf_scores = cosine_similarity(q_vec, self.text_index.tfidf_matrix).flatten()
            for idx, s in enumerate(tf_scores):
                scores[self.text_index.node_ids[idx]] += self.search_weights.get("text", 0.5) * float(s)
        
        # Semantic search
        if self.text_index.embeddings is not None and self.embedding_model is not None and self.text_index.node_ids:
            q_emb = self.embedding_model.encode(query, convert_to_numpy=True)
            sem_scores = cosine_similarity([q_emb], self.text_index.embeddings)[0]
            for idx, s in enumerate(sem_scores):
                scores[self.text_index.node_ids[idx]] += self.search_weights.get("semantic", 0.5) * float(s)
        
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def _reason_about_task(self, request: MemoryRequest) -> Dict[str, Any]:
        """
        Analyze task to generate a focused retrieval query.
        """
        base_query = request.query
        
        if self.model:
            prompt_parts = [
                "Analyze this task to determine what past experience would be most helpful.\n\n",
                f"Task: {base_query}\n",
                f"Status: {request.status.value.upper()}\n"
            ]
            
            if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
                context_preview = request.context[-800:] if len(request.context) > 800 else request.context
                prompt_parts.extend([
                    "\nCurrent Progress:\n",
                    f"{context_preview}\n\n",
                    "Based on progress: What has been attempted? What challenges remain?\n\n"
                ])
            
            prompt_parts.append(
                "Generate a retrieval focus for semantic search over past experience.\n\n"
                "Guidelines:\n"
                "1. Use abstract concepts, not specific details\n"
                "2. Focus on HOW/WHAT-KIND rather than entities\n"
                "3. Include action verbs (e.g., 'handling', 'extracting')\n"
                "4. Describe strategy type, not task itself\n"
                "5. Keep concise: 1-2 sentences max\n\n"
                "Return ONLY JSON:\n"
                '{"retrieval_focus": "your focus here"}'
            )
            
            prompt = "".join(prompt_parts)
            resp = _safe_get_model_response(self.model, prompt)
            if resp:
                try:
                    parsed = json.loads(self._extract_json(resp))
                    if "retrieval_focus" in parsed:
                        return {
                            "retrieval_focus": parsed["retrieval_focus"],
                            "status": request.status.value,
                            "query_text": base_query
                        }
                except Exception:
                    pass
        
        return {
            "retrieval_focus": base_query,
            "status": request.status.value,
            "query_text": base_query
        }

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON object from text if extra tokens present."""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        try:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return m.group(0)
        except Exception:
            pass
        return text

    def _compose_text_guidance(self, request: MemoryRequest, reason: Dict[str, Any], top_nodes: List[NexusNode]) -> str:
        """
        Compose concise, actionable guidance using LLM synthesis.
        """
        if self.model and len(top_nodes) >= 2:
            return self._compose_with_llm_synthesis(request, reason, top_nodes)
        else:
            return self._compose_simple_fallback(request, top_nodes)

    def _compose_with_llm_synthesis(self, request: MemoryRequest, reason: Dict[str, Any], top_nodes: List[NexusNode]) -> str:
        """Use LLM to synthesize retrieved patterns into concise guidance."""
        if request.status == MemoryStatus.BEGIN:
            max_chars = 350
            max_sentences = 2
        elif request.status == MemoryStatus.IN:
            max_chars = 200
            max_sentences = 2
        else:
            max_chars = 400
            max_sentences = 2
        
        retrieved_items = []
        for idx, node in enumerate(top_nodes, 1):
            node_label = f"{node.node_type.upper()}"
            retrieved_items.append(f"{idx}. [{node_label}] {node.content}")
        
        retrieved_text = "\n".join(retrieved_items)
        
        context_info = ""
        if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
            context_preview = request.context[-1200:] if len(request.context) > 1200 else request.context
            context_info = f"\n\nCurrent progress:\n{context_preview}"
        
        if request.status == MemoryStatus.IN:
            no_guidance_instruction = """
NECESSITY CHECK (IN-phase):
ONLY provide guidance if you observe CLEAR SIGNS of difficulty:
✓ Repeated failed attempts or errors
✓ Agent expressing confusion
✓ Stuck in a loop or no progress
✓ Fundamentally wrong approach

DO NOT provide guidance if:
✗ Agent making steady progress
✗ Following reasonable approach
✗ Only minor issues
✗ Task proceeding normally

When in doubt: Return "NO_GUIDANCE_NEEDED"
"""
        else:
            no_guidance_instruction = """
If retrieved patterns are NOT relevant or helpful for this task, return: "NO_GUIDANCE_NEEDED"
"""
        
        prompt = f"""Provide OPTIONAL REFERENCE for an autonomous AI agent.

Task: {request.query}
Status: {request.status.value.upper()}{context_info}

Retrieved patterns:
{retrieved_text}

{no_guidance_instruction}

REQUIREMENTS (if guidance needed):
1. REFERENCE ONLY, NOT instructions
2. Use tentative language: "similar tasks have...", "one approach that worked..."
3. NEVER use "should", "must", "need to"
4. EXACTLY {max_sentences} sentences, under {max_chars} chars
5. Use ABSTRACT terms, avoid specifics
6. Present as observations from past experience
7. Frame as "what has worked before"

Example:
❌ BAD: "You should check the metadata"
✅ GOOD: "Past tasks found data in metadata sources when primary info was absent"

Return only synthesized reference text, no preamble."""

        try:
            synthesized = _safe_get_model_response(self.model, prompt)
            if synthesized and len(synthesized.strip()) > 10:
                synthesized = synthesized.strip()
                
                if "NO_GUIDANCE_NEEDED" in synthesized:
                    return "NO_GUIDANCE_NEEDED"
                
                for prefix in ["Guidance:", "Suggestion:", "Tips:", "Here's", "Here is"]:
                    if synthesized.startswith(prefix):
                        synthesized = synthesized[len(prefix):].lstrip(": ")
                
                if len(synthesized) > max_chars:
                    synthesized = synthesized[:max_chars].rsplit(".", 1)[0].rstrip() + "."
                
                return synthesized
        except Exception:
            pass
        
        return self._compose_simple_fallback(request, top_nodes)

    def _compose_simple_fallback(self, request: MemoryRequest, top_nodes: List[NexusNode]) -> str:
        """Simple fallback composition without LLM."""
        if request.status == MemoryStatus.BEGIN:
            max_chars = 300
            max_items = 2
        elif request.status == MemoryStatus.IN:
            max_chars = 500
            max_items = 3
        else:
            max_chars = 400
            max_items = 2
        
        lines: List[str] = []

        seen_categories = set()
        for node in top_nodes[:max_items]:
            cat = node.metadata.get("category") or node.node_type
            if cat in seen_categories:
                continue
            snippet = node.content.strip()
            if snippet:
                if not any(ref in snippet.lower() for ref in ["past tasks", "similar cases", "previous experience", "has worked", "for reference"]):
                    snippet = f"For reference: similar tasks have {snippet.lower()}"
                lines.append(snippet)
            seen_categories.add(cat)

        if not lines:
            return "NO_GUIDANCE_NEEDED"

        guidance = " ".join(lines)
        if len(guidance) > max_chars:
            guidance = guidance[:max_chars].rsplit(".", 1)[0].rstrip() + "."
        return guidance

    # =========================================================================
    # Tool Memory Path
    # =========================================================================

    def _load_tools(self):
        """Load tools from storage file into registry."""
        if not os.path.exists(self.tools_storage_path):
            return
        
        try:
            spec = importlib.util.spec_from_file_location("nexus_tools", self.tools_storage_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for name in dir(module):
                if name.startswith("_"):
                    continue
                obj = getattr(module, name)
                if callable(obj) and not isinstance(obj, type):
                    self.tools_registry[name] = obj
            
            print(f"[CEREBRA FUSION TOOLS] Loaded {len(self.tools_registry)} tools from storage")
        except Exception as e:
            print(f"[CEREBRA FUSION TOOLS] Error loading tools: {e}")

    def _build_tool_indices(self):
        """Build semantic embeddings for tools."""
        if not self.tools or self.embedding_model is None:
            return
        
        try:
            corpus = []
            tool_names = []
            
            for tool_name, tool in self.tools.items():
                combined_text = f"{tool_name} {tool.description}"
                corpus.append(combined_text)
                tool_names.append(tool_name)
            
            if not corpus:
                return
            
            self.tool_names_index = tool_names
            self.tool_embeddings = self.embedding_model.encode(
                corpus, batch_size=32, convert_to_numpy=True, show_progress_bar=False
            )
            print(f"[CEREBRA FUSION TOOLS] Built embeddings for {len(corpus)} tools")
        except Exception as e:
            print(f"[CEREBRA FUSION TOOLS] Error building tool indices: {e}")

    def _search_tools(self, query: str) -> List[Dict[str, Any]]:
        """Semantic search for relevant tools, returning TOP-3 candidates."""
        if self.tool_embeddings is None or self.embedding_model is None or not self.tool_names_index:
            return []
        
        try:
            q_emb = self.embedding_model.encode(query, convert_to_numpy=True)
            similarities = cosine_similarity([q_emb], self.tool_embeddings)[0]
            
            candidates = []
            for idx, similarity in enumerate(similarities):
                tool_name = self.tool_names_index[idx]
                if tool_name not in self.tools:
                    continue
                
                tool = self.tools[tool_name]
                candidates.append({
                    "name": tool_name,
                    "description": tool.description,
                    "score": float(similarity),
                    "domain": tool.domain,
                    "tags": tool.tags,
                })
            
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:self.max_tool_candidates]
        except Exception:
            return []

    def _tool_router(self, request: MemoryRequest, candidates: List[Dict[str, Any]]) -> List[str]:
        """
        Independent tool router: decides which tools (if any) to provide.
        Uses LLM with simplified, context-aware prompt.
        """
        if not self.model or not candidates:
            return []
        
        try:
            candidate_lines = []
            for i, c in enumerate(candidates, 1):
                candidate_lines.append(
                    f"{i}. {c['name']}: {c['description'][:100]} (score: {c['score']:.2f})"
                )
            
            context_preview = ""
            if hasattr(request, 'context') and request.context:
                context_preview = request.context[-600:] if len(request.context) > 600 else request.context
            
            prompt = f"""You are a tool selection agent. Decide which tools (if any) would help with this task.

Task: {request.query}
Phase: {request.status.value}
Context: {context_preview}

Available Tools:
{chr(10).join(candidate_lines)}

Rules:
- Return EMPTY list [] if no tool is clearly helpful
- Maximum 2 tools
- Only select if tool directly addresses task needs
- Consider current phase and context

Return ONLY a JSON list: ["tool1", "tool2"] or []

Your selection:"""

            response = _safe_get_model_response(self.model, prompt)
            if not response:
                return []
            
            selected = json.loads(response.strip())
            if isinstance(selected, list):
                valid_names = [str(name) for name in selected if str(name) in {c["name"] for c in candidates}]
                return valid_names[:2]
        except Exception:
            pass
        
        return []

    def _wrap_tool(self, tool_func: Callable, tool_name: str) -> Any:
        """Wrap Python function as Tool object."""
        if self.tool_wrapper:
            return self.tool_wrapper.wrap_function(tool_func, tool_name)
        return None

    # =========================================================================
    # Main API: Provide Memory
    # =========================================================================

    def provide_memory(self, request: MemoryRequest) -> MemoryResponse:
        """
        Provide memory using parallel text and tool routing:
        1) Text Path: Reason -> Retrieve -> Graph Expand -> Compose
        2) Tool Path: Search -> Router -> Wrap (if enabled)
        """
        try:
            memories = []
            
            # ===== TEXT MEMORY PATH =====
            reason = self._reason_about_task(request)
            retrieval_query = reason.get("retrieval_focus", request.query)
            
            if request.status == MemoryStatus.IN and hasattr(request, 'context') and request.context:
                retrieval_query = f"{retrieval_query} continuation resume partial progress"

            pairs = self._hybrid_search(retrieval_query, top_k=self.top_k)
            expanded_pairs, edges_used = self._graph_expand(pairs, retrieval_query)
            
            threshold = self.min_score_in_phase if request.status == MemoryStatus.IN else self.min_score
            filtered_pairs = [(nid, score) for nid, score in expanded_pairs if score >= threshold]
            
            # Track used nodes and edges for success rate calculation
            request_id = str(uuid.uuid4())
            used_node_ids = []
            used_edge_pairs = []
            
            if filtered_pairs:
                filtered_pairs = filtered_pairs[:self.top_k]
                top_nodes = [self.nodes[nid] for nid, _ in filtered_pairs]
                used_node_ids = [n.id for n in top_nodes]
                used_edge_pairs = edges_used  # Edges used in graph expansion
                
                guidance_text = self._compose_text_guidance(request, reason, top_nodes)
                
                if guidance_text != "NO_GUIDANCE_NEEDED":
                    label = "Past Experience (for reference)" if request.status == MemoryStatus.IN else "Context Note"
                    
                    memory_item = MemoryItem(
                        id=f"cerebra_fusion_text_{uuid.uuid4()}",
                        content=f"[{label}] {guidance_text}",
                        metadata={
                            "status": request.status.value,
                            "original_query": request.query,
                            "retrieval_focus": reason.get("retrieval_focus", ""),
                            "top_node_ids": [n.id for n in top_nodes],
                            "is_reference_only": True,
                        },
                        score=float(sum(s for _, s in filtered_pairs) / max(1, len(filtered_pairs))),
                        type=MemoryItemType.TEXT
                    )
                    memories.append(memory_item)
            
            # Store usage tracking (will be updated when task completes)
            self.active_usage_tracking[request_id] = {
                "node_ids": used_node_ids,
                "edge_pairs": used_edge_pairs,
                "query": request.query,
            }
            
            # ===== TOOL MEMORY PATH (if enabled) =====
            if self.enable_tool_memory and self.tools:
                tool_candidates = self._search_tools(request.query)
                if tool_candidates:
                    selected_tool_names = self._tool_router(request, tool_candidates)
                    
                    for tool_name in selected_tool_names:
                        tool_func = self.tools_registry.get(tool_name)
                        if not tool_func:
                            continue
                        
                        wrapped_tool = self._wrap_tool(tool_func, tool_name)
                        if not wrapped_tool:
                            continue
                        
                        tool = self.tools[tool_name]
                        memory_item = MemoryItem(
                            id=f"cerebra_fusion_tool_{tool_name}",
                            content=f"Cerebra Fusion Tool: {tool_name}\n{tool.description}",
                            metadata={
                                "source": "cerebra_fusion_tool",
                                "tool_name": tool_name,
                                "wrapped_tool": wrapped_tool,
                                "callable": tool_func,
                            },
                            type=MemoryItemType.API,
                        )
                        memories.append(memory_item)
                        
                        # Update usage stats
                        tool.usage_count += 1
            
            return MemoryResponse(
                memories=memories,
                memory_type=self._get_declared_memory_type(),
                total_count=len(memories),
                request_id=request_id  # Use the tracked request_id
            )
        except Exception as e:
            print(f"[CEREBRA FUSION] Error in provide_memory: {e}")
            return MemoryResponse(
                memories=[],
                memory_type=self._get_declared_memory_type(),
                total_count=0,
                request_id=str(uuid.uuid4())
            )

    # =========================================================================
    # Main API: Take In Memory
    # =========================================================================

    def take_in_memory(self, trajectory_data: TrajectoryData) -> Tuple[bool, str]:
        """
        Ingest successful task memory into graph and tools.
        - Extract text patterns (max ~10 nodes)
        - Extract tool function if applicable
        - Build semantic edges
        - Update success counts for previously used memories
        - Trigger consolidation periodically
        """
        try:
            is_success = self._is_success(trajectory_data)
            
            # Update success counts for memories used in this task
            # Match by query (approximate matching)
            task_query = trajectory_data.query
            self._update_memory_success_counts(task_query, is_success)
            
            if not is_success:
                return True, "Skipped: only successful tasks are ingested"
            
            absorbed_items = []
            
            # ===== TEXT MEMORY INGESTION =====
            summary = self._summarize_trajectory(trajectory_data)
            if summary:
                nodes_created = self._store_text_memories(summary, trajectory_data)
                absorbed_items.extend([f"text:{n.id[:8]}" for n in nodes_created])
            
            # ===== TOOL MEMORY INGESTION (if enabled) =====
            if self.enable_tool_memory:
                tool_info = self._extract_tool(trajectory_data)
                if tool_info:
                    tool_stored = self._store_tool(tool_info)
                    if tool_stored:
                        absorbed_items.append(f"tool:{tool_info['name']}")
            
            # Persist changes
            self._persist_db()
            
            # Periodic consolidation
            self.task_counter += 1
            if self.task_counter >= self.consolidation_interval:
                self._consolidate_memory()
                self.task_counter = 0
            
            return True, f"Ingested {len(absorbed_items)} items: {', '.join(absorbed_items[:5])}"
            
        except Exception as e:
            return False, f"Ingestion error: {e}"

    def _is_success(self, trajectory_data: TrajectoryData) -> bool:
        """Determine success from trajectory metadata."""
        md = trajectory_data.metadata or {}
        if 'is_correct' in md:
            return md['is_correct'] is True
        if 'success' in md:
            return md['success'] is True
        if 'task_success' in md:
            return md['task_success'] is True
        if 'failed' in md:
            return md['failed'] is False
        return False

    def _summarize_trajectory(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, Any]]:
        """Extract abstract patterns from trajectory."""
        traj_text = self._format_trajectory(trajectory_data)
        
        prompt = f"""Extract ABSTRACT, GENERALIZABLE patterns from this successful task.

Question: {trajectory_data.query}

Execution:
{traj_text}

ABSTRACTION REQUIREMENTS:
1. Extract STRATEGY TYPES, not implementations
2. Use GENERIC terminology:
   - Say "metadata sources" NOT "JSON-LD"
   - Say "alternate access methods" NOT "Wayback Machine"
3. Focus on WHEN/WHY patterns apply
4. Brief patterns (1 sentence each)
5. Make patterns applicable to similar tasks
6. LIMIT: max 4 patterns, max 3 playbooks, max 2 checklists

Return JSON:
- "highlights": 2-3 sentence abstract summary
- "patterns": list of top 4 ABSTRACT patterns
- "playbooks": dict of up to 3 GENERAL DOMAINS -> brief tips
- "checklists": list of top 2 brief confirmation steps
"""
        
        resp = _safe_get_model_response(self.model, prompt)
        
        if resp:
            try:
                json_str = self._extract_json(resp)
                parsed = json.loads(json_str)
                
                for key in ["highlights", "patterns", "playbooks", "checklists"]:
                    if key not in parsed:
                        parsed[key] = [] if key != "highlights" else ""
                
                return parsed
            except Exception:
                pass
        
        return {
            "highlights": f"Execution for: {trajectory_data.query[:100]}",
            "patterns": [],
            "playbooks": {},
            "checklists": []
        }

    def _format_trajectory(self, trajectory_data: TrajectoryData) -> str:
        """Simple formatter for trajectory steps."""
        if not trajectory_data.trajectory:
            return "No trajectory available."
        parts = []
        for i, step in enumerate(trajectory_data.trajectory, 1):
            stype = step.get("type", "step")
            content = step.get("content", "")
            parts.append(f"{i}. [{stype}] {content}")
        return "\n".join(parts)

    def _store_text_memories(self, summary: Dict[str, Any], trajectory_data: TrajectoryData) -> List[NexusNode]:
        """Store extracted text memories to graph."""
        nodes_created = []
        base_meta = {"source_query": trajectory_data.query}
        max_total_nodes = 10
        
        # Success node
        content = summary.get("highlights", "")
        if content:
            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="success",
                content=content,
                metadata={**base_meta, "outcome": "success"},
                signature=self._compute_signature(content)
            )
            
            # Check for duplicates
            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Patterns (limit to 4)
        for p in summary.get("patterns", [])[:4]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = p if isinstance(p, str) else " ".join(str(x) for x in p) if isinstance(p, (list, tuple)) else str(p)
            content = content.strip()
            
            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="pattern",
                content=content,
                metadata=base_meta,
                signature=self._compute_signature(content)
            )
            
            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Playbooks (limit to 3)
        for content_type, tips in list(summary.get("playbooks", {}).items())[:3]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = tips if isinstance(tips, str) else " ".join(str(x) for x in tips) if isinstance(tips, (list, tuple)) else str(tips)
            content = content.strip()
            
            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="playbook",
                content=content,
                metadata={**base_meta, "content_type": content_type},
                signature=self._compute_signature(content)
            )
            
            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node

        # Checklists (limit to 2)
        for c in summary.get("checklists", [])[:2]:
            if len(nodes_created) >= max_total_nodes:
                break
            content = c if isinstance(c, str) else " ".join(str(x) for x in c) if isinstance(c, (list, tuple)) else str(c)
            content = content.strip()
            
            node = NexusNode(
                id=str(uuid.uuid4()),
                node_type="checklist",
                content=content,
                metadata=base_meta,
                signature=self._compute_signature(content)
            )
            
            if not self._find_node_by_signature(node.signature):
                nodes_created.append(node)
                self.nodes[node.id] = node
        
        # Create SAME_TASK edges
        if len(nodes_created) > 1:
            anchor_id = nodes_created[0].id
            for node in nodes_created[1:]:
                self.edges.append(NexusEdge(
                    source=anchor_id,
                    target=node.id,
                    edge_type=EdgeType.SAME_TASK,
                    weight=1.0,
                    metadata={"task_query": trajectory_data.query}
                ))

        # Rebuild indices
        self._finalize_indices()
        
        # Build semantic edges
        total_semantic_edges = 0
        for node in nodes_created:
            if node.node_type in ['pattern', 'playbook', 'checklist']:
                total_semantic_edges += self._build_semantic_edges(node)
        
        print(f"[CEREBRA FUSION INGEST] Added {len(nodes_created)} nodes, {total_semantic_edges} semantic edges")
        return nodes_created

    def _extract_tool(self, trajectory_data: TrajectoryData) -> Optional[Dict[str, Any]]:
        """Extract reusable tool from trajectory."""
        if not self.model:
            return None
        
        try:
            trajectory_str = json.dumps(trajectory_data.trajectory or [], ensure_ascii=False)
            
            prompt = f"""Create a REUSABLE, GENERIC tool function from this successful task.

Task: {trajectory_data.query}
Trajectory: {trajectory_str}
Result: {str(trajectory_data.result)}

REQUIREMENTS:
1. PARAMETERIZED function with inputs, NOT hardcoded values
2. Focus on METHODOLOGY, not specific data
3. GENERIC and applicable to similar problems
4. Use ONLY simple type hints: str, int, float, bool, list, dict
5. NO complex types: Callable, Union, Optional, Any

Return ONLY Python code:

```python
def your_function(param1: str, param2: int) -> str:
    \"\"\"
    Brief description.
    
    Args:
        param1: Description
        param2: Description
    
    Returns:
        Description
    \"\"\"
    # Implementation
    return "result"
```

Your function:"""

            response = _safe_get_model_response(self.model, prompt)
            if not response:
                return None
            
            # Try to extract code from markdown code blocks first
            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if not code_match:
                code_match = re.search(r"```\n(.*?)```", response, re.DOTALL)
            
            if code_match:
                code = code_match.group(1).strip()
            else:
                # Fallback: try to extract function definition directly
                # Look for function definition pattern: def function_name(...):
                func_match = re.search(r"def\s+\w+\s*\([^)]*\)\s*:.*?(?=\n\n|\ndef\s+|\Z)", response, re.DOTALL)
                if func_match:
                    code = func_match.group(0).strip()
                    # Try to extract complete function (including docstring and body)
                    # If the match seems incomplete, try to get more context
                    if code.count('\n') < 3:  # Likely incomplete, try to get more
                        # Look for function with more context
                        extended_match = re.search(
                            r"(def\s+\w+\s*\([^)]*\)\s*:.*?)(?=\n\ndef\s+|\nclass\s+|\Z)", 
                            response, 
                            re.DOTALL
                        )
                        if extended_match:
                            code = extended_match.group(1).strip()
                else:
                    return None
            
            if self._is_dangerous_code(code):
                return None
            
            func_info = self._extract_function_info(code)
            if not func_info:
                return None
            
            return {
                "name": func_info["name"],
                "code": code,
                "description": func_info.get("description", ""),
                "domain": "general",
            }
        except Exception:
            return None

    def _store_tool(self, tool_info: Dict[str, Any]) -> bool:
        """Store tool to registry and file."""
        try:
            tool_name = tool_info["name"]
            code = tool_info["code"]
            
            # Check duplicates
            signature = self._compute_signature(code)
            if any(t.signature == signature for t in self.tools.values()):
                return False
            
            # Append to storage file
            self._append_tool_to_storage(tool_name, code)
            
            # Create tool record
            tool = ToolRecord(
                name=tool_name,
                description=tool_info.get("description", ""),
                code=code,
                domain=tool_info.get("domain", "general"),
                tags=self._extract_tags(code),
                signature=signature
            )
            self.tools[tool_name] = tool
            
            # Reload registry
            self._load_tools()
            
            # Rebuild tool indices
            self._build_tool_indices()
            
            print(f"[CEREBRA FUSION TOOLS] Stored tool: {tool_name}")
            return True
        except Exception:
            return False

    def _append_tool_to_storage(self, tool_name: str, code: str) -> None:
        """Append tool code to storage file."""
        os.makedirs(os.path.dirname(self.tools_storage_path) or ".", exist_ok=True)
        
        if os.path.exists(self.tools_storage_path):
            with open(self.tools_storage_path, "r", encoding="utf-8") as f:
                existing = f.read()
        else:
            existing = '"""\nCerebra Fusion Memory API Tools\nDynamically generated tools\n"""\n\n'
        
        if f"def {tool_name}(" in existing:
            return
        
        new_content = existing + f"\n{code}\n\n"
        
        with open(self.tools_storage_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    # =========================================================================
    # Memory Consolidation
    # =========================================================================

    def _consolidate_memory(self):
        """
        Consolidate memory graph:
        1. Merge highly similar nodes
        2. Prune low-performance edges
        3. Optimize edge weights
        """
        print("[CEREBRA FUSION CONSOLIDATE] Starting memory consolidation...")
        
        # 1. Merge similar nodes
        merged_count = self._merge_similar_nodes()
        
        # 2. Prune ineffective edges
        pruned_count = self._prune_edges()
        
        # 3. Optimize edge weights
        self._optimize_edge_weights()
        
        # Rebuild indices after consolidation
        self._finalize_indices()
        if self.enable_tool_memory:
            self._build_tool_indices()
        
        # Persist changes
        self._persist_db()
        
        print(f"[CEREBRA FUSION CONSOLIDATE] Complete: merged {merged_count} nodes, pruned {pruned_count} edges")

    def _merge_similar_nodes(self) -> int:
        """Merge highly similar nodes to reduce redundancy."""
        if self.embedding_model is None or self.text_index.embeddings is None:
            return 0
        
        merged_count = 0
        merge_threshold = 0.7  # High similarity
        
        nodes_to_merge = []
        processed = set()
        
        for i, node_id_a in enumerate(self.text_index.node_ids):
            if node_id_a in processed:
                continue
            
            node_a = self.nodes.get(node_id_a)
            if not node_a:
                continue
            
            emb_a = self.text_index.embeddings[i]
            
            for j, node_id_b in enumerate(self.text_index.node_ids[i+1:], i+1):
                if node_id_b in processed:
                    continue
                
                node_b = self.nodes.get(node_id_b)
                if not node_b or node_b.node_type != node_a.node_type:
                    continue
                
                emb_b = self.text_index.embeddings[j]
                similarity = cosine_similarity([emb_a], [emb_b])[0][0]
                
                if similarity >= merge_threshold:
                    nodes_to_merge.append((node_id_a, node_id_b))
                    processed.add(node_id_b)
                    merged_count += 1
        
        # Perform merges
        for keep_id, remove_id in nodes_to_merge:
            # Redirect edges
            for edge in self.edges:
                if edge.source == remove_id:
                    edge.source = keep_id
                if edge.target == remove_id:
                    edge.target = keep_id
            
            # Remove node
            if remove_id in self.nodes:
                del self.nodes[remove_id]
        
        return merged_count

    def _prune_edges(self) -> int:
        """Prune edges with low performance."""
        pruned_count = 0
        min_usage_for_pruning = 10
        min_success_rate = 0.2
        
        edges_to_keep = []
        for edge in self.edges:
            # Keep SAME_TASK edges
            if edge.edge_type == EdgeType.SAME_TASK:
                edges_to_keep.append(edge)
                continue
            
            # Prune edges with poor performance
            if edge.usage_count >= min_usage_for_pruning:
                success_rate = edge.success_count / edge.usage_count if edge.usage_count > 0 else 0
                if success_rate < min_success_rate:
                    pruned_count += 1
                    continue
            
            edges_to_keep.append(edge)
        
        self.edges = edges_to_keep
        return pruned_count

    def _optimize_edge_weights(self):
        """Adjust edge weights based on usage success rate."""
        adjusted_count = 0
        for edge in self.edges:
            if edge.usage_count > 5:
                success_rate = edge.success_count / edge.usage_count
                
                if success_rate > 0.6:
                    edge.weight = min(1.0, edge.weight * (1.0 + 0.2 * (success_rate - 0.6) / 0.4))
                    adjusted_count += 1
                elif success_rate < 0.4:
                    edge.weight = max(0.5, edge.weight * (1.0 - 0.2 * (0.4 - success_rate) / 0.4))
                    adjusted_count += 1
        
        if adjusted_count > 0:
            print(f"[CEREBRA FUSION OPTIMIZE] Adjusted {adjusted_count} edge weights")

    # =========================================================================
    # Helper Functions
    # =========================================================================

    def _update_memory_success_counts(self, task_query: str, is_success: bool):
        """Update success counts for memories used in this task."""
        try:
            # Find matching usage tracking by query similarity
            # Simple approach: match by query (exact or substring)
            matched_tracking = None
            for request_id, tracking in list(self.active_usage_tracking.items()):
                # Match if query is similar (exact match or one contains the other)
                tracking_query = tracking.get("query", "")
                if (task_query == tracking_query or 
                    task_query in tracking_query or 
                    tracking_query in task_query):
                    matched_tracking = tracking
                    # Remove from active tracking (one-time update)
                    del self.active_usage_tracking[request_id]
                    break
            
            if not matched_tracking:
                # No matching tracking found, skip
                return
            
            # Update edge success counts
            edge_pairs = matched_tracking.get("edge_pairs", [])
            for source, target in edge_pairs:
                for edge in self.edges:
                    if edge.source == source and edge.target == target:
                        if is_success:
                            edge.success_count += 1
                        # usage_count was already incremented in _graph_expand
                        break
            
            if edge_pairs and is_success:
                print(f"[CEREBRA FUSION] Updated success counts for {len(edge_pairs)} edges")
        except Exception as e:
            # Don't fail the whole ingestion if tracking fails
            print(f"[CEREBRA FUSION] Warning: Failed to update success counts: {e}")

    def _compute_signature(self, text: str) -> str:
        """Compute text signature for deduplication."""
        normalized = re.sub(r"\s+", " ", (text or "")).strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _find_node_by_signature(self, signature: str) -> Optional[str]:
        """Find node by signature."""
        for node_id, node in self.nodes.items():
            if node.signature == signature:
                return node_id
        return None

    def _extract_function_info(self, code: str) -> Optional[Dict[str, str]]:
        """Extract function information from code."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    name = node.name
                    docstring = ast.get_docstring(node) or ""
                    description = docstring.split('\n')[0] if docstring else name
                    return {
                        "name": name,
                        "description": description,
                    }
        except Exception:
            pass
        return None

    def _is_dangerous_code(self, code: str) -> bool:
        """Check if code contains dangerous operations."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in {"exec", "eval", "compile", "__import__", "open"}:
                            return True
                if isinstance(node, ast.Attribute):
                    if node.attr in {"system", "popen", "spawn", "remove", "rmdir", "unlink"}:
                        return True
        except Exception:
            return True
        return False

    def _extract_tags(self, text: str) -> List[str]:
        """Extract tags from text."""
        tags = []
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in ["search", "retrieve", "find"]):
            tags.append("search")
        if any(kw in text_lower for kw in ["calculate", "compute", "count"]):
            tags.append("computation")
        if any(kw in text_lower for kw in ["validate", "verify", "check"]):
            tags.append("validation")
        if any(kw in text_lower for kw in ["error", "fallback", "handle"]):
            tags.append("error_handling")
        
        return list(set(tags))

