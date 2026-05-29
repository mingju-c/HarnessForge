from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'mutation_closure_react'
ACTION_MODULE = 'mutation_closure_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'soft',
    'complete_gate': True,
    'completion_policy': 'mutation',
    'drop_extra_keys': True,
    'repeat_limit': 1,
    'partial_commit_on_blocker': True,
    'min_successful_mutations_before_partial_complete': 2,
    'enable_ledger_review_tool': True,
    'focus': 'stateful mutation closure ledger with cautious completion',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
