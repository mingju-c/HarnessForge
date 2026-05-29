from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'failsoft_recovery_react'
ACTION_MODULE = 'failsoft_recovery_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'soft',
    'complete_gate': False,
    'completion_policy': 'progress',
    'drop_extra_keys': True,
    'repeat_limit': 1,
    'partial_commit_on_blocker': True,
    'min_successful_mutations_before_partial_complete': 1,
    'enable_ledger_review_tool': True,
    'focus': 'fail-soft recovery router after schema, not-found, repeat, and empty-action blockers',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
