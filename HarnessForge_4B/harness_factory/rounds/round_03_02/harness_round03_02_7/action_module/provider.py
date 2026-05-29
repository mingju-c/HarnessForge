from __future__ import annotations

from .round03_agent import Round03ActionProvider, Round03GuardedAgent


ACTION_SYSTEM = "risk_review_react"
ACTION_MODULE = "risk_review_react"


class ActionProvider(Round03ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 4
    VARIANT_CONFIG = {'support_record_gate': True,
 'support_mode': 'route',
 'complete_gate': True,
 'completion_policy': 'verified_mutation_closure',
 'drop_extra_keys': True,
 'repeat_limit': 2,
 'partial_commit_on_blocker': True,
 'partial_mode': 'exceptional',
 'partial_guard_events': 2,
 'min_successful_mutations_before_partial_complete': 1,
 'planned_mutation_cap': 3,
 'enable_ledger_review_tool': True,
 'date_iso_canonicalization': True,
 'searchqa_minimal_span': True,
 'searchqa_overlong_token_limit': 15,
 'transform_requires_current_evidence': True,
 'memory_argument_quarantine': True,
 'focus': 'triggered non-acting verification'}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round03GuardedAgent"]
