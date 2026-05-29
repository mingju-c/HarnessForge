"""
Configuration for EvolveLab memory system
"""

from typing import Dict, Any
import os
from .memory_types import MemoryType

# Default configuration for different memory providers
STORAGE_BASE_DIR = "./storage"
COMMON_PROVIDER_CONFIG = {
    # Shared switch across all memory providers.
    # True means "write-only": store new memory but never retrieve old memory.
    "write_only": False,
}

DEFAULT_CONFIG = {
    "EvolveLab": {
        "default_top_k": 3,
        "active_provider": "agent_kb",  # Default active provider
        "storage_base_dir": STORAGE_BASE_DIR,
    },
    
    "providers": {
        MemoryType.AGENT_KB: {
            "kb_database_path": os.path.join(STORAGE_BASE_DIR, "agent_kb", "agent_kb_database.json"),
            "top_k": 3,
            "search_weights": {'text': 0.5, 'semantic': 0.5},
        },
        
        MemoryType.SKILLWEAVER: {
            "skills_file_path": os.path.join(STORAGE_BASE_DIR, "skillweaver", "skillweaver_generated_skills.py"),
            "skills_dir": os.path.join(STORAGE_BASE_DIR, "skillweaver"),
        },
        
        MemoryType.MOBILEE: {
            "tips_file_path": os.path.join(STORAGE_BASE_DIR, "mobilee", "tips", "tips.json"),
            "shortcuts_file_path": os.path.join(STORAGE_BASE_DIR, "mobilee", "shortcuts", "shortcuts.json"),
        },
        
        MemoryType.EXPEL: {
            "insights_file_path": os.path.join(STORAGE_BASE_DIR, "expel", "insights.json"),
            "success_trajectories_file_path": os.path.join(STORAGE_BASE_DIR, "expel", "success_trajectories.json"),
            "top_k": 3,
            "search_weights": {'text': 0.3, 'semantic': 0.7},
            # embedding model id for sentence-transformers (optional override)
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_model_cache": "./storage/models"
        },
        MemoryType.LIGHTWEIGHT_MEMORY: {
            "model": None,
            "storage_dir": "./storage/lightweight_memory",
            "max_strategic_memories": 30,
            "max_operational_memories": 30,
            "max_shortterm_items": 15,
            "shortterm_provision_interval": 5,
            "top_k_longterm": 3,
            "enable_longterm_provision": True,
        },
        MemoryType.CEREBRA_FUSION_MEMORY: {
            "model": None,
            "storage_dir": "./storage/cerebra_fusion_memory",
            "db_path": "./storage/cerebra_fusion_memory/cf_database.json",
            "model_cache_dir": "./storage/models",
            "top_k": 3,
            "search_weights": {"text": 0.2, "semantic": 0.8},
            "min_score": 0.0,
            "min_score_in_phase": 0.0,
            "semantic_edge_threshold": 0.75,
            "max_neighbors_expand": 3,
            "enable_graph_expansion": True,
            "enable_tool_memory": True,
            "tools_storage_path": "./storage/cerebra_fusion_memory/tools_storage.py",
            "max_tool_candidates": 3,
            "consolidation_interval": 50,
        },
        MemoryType.DILU: {
            "db_path": "./storage/dilu/dilu_memory.json",      
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_model_cache": "./storage/models"
        },
        MemoryType.GENERATIVE: {
            "db_path": "./storage/generative/generative_memory.json",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_model_cache": "./storage/models"
        },
        MemoryType.VOYAGER: {
            "db_path": "./storage/voyager/voyager_memory.json",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_model_cache": "./storage/models"
        },
        MemoryType.MEMP: {
            "store_path": os.path.join(STORAGE_BASE_DIR, "memp"),
            "records_file": "procedural_records.json",
        },
        MemoryType.DYNAMIC_CHEATSHEET: {
            "store_path": "./storage/dynamic_cheatsheet",
            "records_file": "dynamic_cheatsheet.json",
            "cheatsheet_file": "global_cheatsheet.txt",
            "top_k": 1,
        },
        MemoryType.AGENT_WORKFLOW_MEMORY: {
            "store_path": "./storage/agent_workflow_memory/workflow_memory.json",
            "index_dir": "./storage/agent_workflow_memory/index",
            "top_k": 1,
            "enable_induction": True,
        },
        MemoryType.EVOLVER: {
            "store_path": "./storage/evolver",
            "records_file": "principle_records.json",
            "search_top_k": 1,
            "max_pos_examples": 1,
            "max_neg_examples": 1,
            "prune_threshold": 0.3,
        },
        # add new memory type upside this line
}
}


def get_memory_config(provider_type: MemoryType) -> Dict[str, Any]:
    """Get configuration for a specific memory provider"""
    config = COMMON_PROVIDER_CONFIG.copy()
    config.update(DEFAULT_CONFIG["providers"].get(provider_type, {}).copy())
    return config


def get_evolve_lab_config() -> Dict[str, Any]:
    """Get configuration for the EvolveLab memory system"""
    return DEFAULT_CONFIG["EvolveLab"].copy()
