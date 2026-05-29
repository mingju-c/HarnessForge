from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'light_verifier_react'
ACTION_MODULE = 'light_verifier_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 6
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'route',
    'complete_gate': False,
    'completion_policy': 'progress',
    'drop_extra_keys': True,
    'repeat_limit': 1,
    'partial_commit_on_blocker': True,
    'min_successful_mutations_before_partial_complete': 1,
    'enable_ledger_review_tool': False,
    'focus': 'low-overhead verifier with schema cooldown and support recording',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
