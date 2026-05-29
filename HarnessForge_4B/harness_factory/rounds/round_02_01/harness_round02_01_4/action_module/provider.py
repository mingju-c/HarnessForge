from __future__ import annotations

from .round02_agent import Round02ActionProvider, Round02GuardedAgent


ACTION_SYSTEM = 'hop_provenance_react'
ACTION_MODULE = 'hop_provenance_react'


class ActionProvider(Round02ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 4
    VARIANT_CONFIG = {
        'support_record_gate': True,
    'support_mode': 'strict',
    'complete_gate': False,
    'completion_policy': 'progress',
    'drop_extra_keys': True,
    'repeat_limit': 1,
    'partial_commit_on_blocker': False,
    'enable_ledger_review_tool': False,
    'focus': 'multi-hop provenance ledger with strict answer support',
    }


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round02GuardedAgent"]
