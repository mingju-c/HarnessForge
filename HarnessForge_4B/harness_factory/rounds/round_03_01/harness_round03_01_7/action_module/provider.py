from __future__ import annotations

from .round03_agent import Round03ActionProvider, Round03LedgerAgent


ACTION_SYSTEM = 'round03_checkpoint_react'
ACTION_MODULE = 'round03_checkpoint_react'


class ActionProvider(Round03ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {'support_mode': 'strict', 'relation_min_overlap': 2, 'completion_policy': 'mutation_coverage', 'mutation_coverage_cap': 4, 'repeat_limit': 1, 'enable_ledger_review_tool': True, 'partial_commit_on_blocker': False}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round03LedgerAgent"]
