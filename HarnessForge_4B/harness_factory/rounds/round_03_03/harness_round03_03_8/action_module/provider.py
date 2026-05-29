from __future__ import annotations

from .round03_03_agent import Round0303ActionProvider, Round0303GuardedAgent


ACTION_SYSTEM = "commit_audit_react"
ACTION_MODULE = ACTION_SYSTEM


class ActionProvider(Round0303ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 5
    VARIANT_CONFIG = {'cap_planned_mutations': False,
 'complete_gate': True,
 'completion_policy': 'verified_or_slots',
 'date_iso_canonicalization': True,
 'deterministic_transform_support': True,
 'drop_extra_keys': True,
 'enable_ledger_review_tool': True,
 'focus': 'read-only commit audit with strict slot support and all-slot completion',
 'min_success_before_complete': 1,
 'partial_commit_on_blocker': False,
 'planned_mutation_cap': 0,
 'relation_min_overlap': 1,
 'repeat_limit': 2,
 'support_mode': 'strict_slot',
 'support_record_gate': True}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round0303GuardedAgent"]
