from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'format_contract_react'
ACTION_MODULE = 'format_contract_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'route',
    'complete_gate': True,
    'completion_policy': 'progress',
    'drop_extra_keys': True,
    'repeat_limit': 2,
    'partial_commit_on_blocker': True,
    'min_successful_mutations_before_partial_complete': 1,
    'date_iso_canonicalization': True,
    'enable_ledger_review_tool': False,
    'focus': 'active terminal and exact-format contract with date canonicalization',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
