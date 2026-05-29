from __future__ import annotations

from .round03_agent import Round03ActionProvider, Round03LedgerAgent


ACTION_SYSTEM = 'round03_recovery_router_react'
ACTION_MODULE = 'round03_recovery_router_react'


class ActionProvider(Round03ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {'support_mode': 'strict', 'relation_min_overlap': 1, 'completion_policy': 'mutation_coverage', 'mutation_coverage_cap': 3, 'repeat_limit': 1, 'repair_missing_from_evidence': True, 'repair_unknown_tool_name': True, 'partial_commit_on_blocker': False}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round03LedgerAgent"]
