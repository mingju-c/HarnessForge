from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'evidence_search_react'
ACTION_MODULE = 'evidence_search_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 4
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'strict',
    'complete_gate': True,
    'completion_policy': 'progress',
    'drop_extra_keys': False,
    'repeat_limit': 2,
    'partial_commit_on_blocker': True,
    'min_successful_mutations_before_partial_complete': 1,
    'enable_ledger_review_tool': False,
    'focus': 'retrieval evidence arbitration before final answers',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
