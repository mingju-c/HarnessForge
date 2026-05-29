from __future__ import annotations

from .round03_agent import Round03ActionProvider, Round03LedgerAgent


ACTION_SYSTEM = 'round03_light_contract_react'
ACTION_MODULE = 'round03_light_contract_react'


class ActionProvider(Round03ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {'support_mode': 'route', 'relation_min_overlap': 0, 'strict_single_token_support': False, 'completion_policy': 'mutation_coverage', 'mutation_coverage_cap': 2, 'repeat_limit': 2, 'partial_commit_on_blocker': True, 'min_successful_mutations_before_partial_complete': 2}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round03LedgerAgent"]
