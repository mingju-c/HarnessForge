from __future__ import annotations

from .round03_agent import Round03ActionProvider, Round03GuardedAgent


ACTION_SYSTEM = "raw_span_react"
ACTION_MODULE = "raw_span_react"


class ActionProvider(Round03ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 4
    VARIANT_CONFIG = {'support_record_gate': True,
 'support_mode': 'strict',
 'complete_gate': True,
 'completion_policy': 'ledger_or_progress',
 'drop_extra_keys': True,
 'repeat_limit': 2,
 'partial_commit_on_blocker': True,
 'partial_mode': 'base',
 'min_successful_mutations_before_partial_complete': 1,
 'planned_mutation_cap': 2,
 'enable_ledger_review_tool': False,
 'date_iso_canonicalization': True,
 'searchqa_minimal_span': True,
 'searchqa_overlong_token_limit': 10,
 'transform_requires_current_evidence': False,
 'memory_argument_quarantine': True,
 'focus': 'raw-span final answer canonicalization'}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round03GuardedAgent"]
