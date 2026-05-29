from __future__ import annotations

from .round03_04_agent import Round0304ActionProvider, Round0304GuardedAgent


ACTION_SYSTEM = "soft_generalist_react"
ACTION_MODULE = ACTION_SYSTEM


class ActionProvider(Round0304ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 6
    VARIANT_CONFIG = {'cap_planned_mutations': False,
 'complete_gate': True,
 'completion_policy': 'all_slots',
 'date_iso_canonicalization': True,
 'deterministic_transform_support': True,
 'drop_extra_keys': True,
 'enable_ledger_review_tool': False,
 'min_success_before_complete': 1,
 'min_successful_mutations_before_partial_complete': 1,
 'partial_commit_on_blocker': False,
 'planned_mutation_cap': 0,
 'relation_min_overlap': 1,
 'repeat_limit': 2,
 'slot_match_fallback': True,
 'support_record_gate': True,
 'support_mode': 'balanced_slot',
 'focus': 'soft generalist route ledger with balanced support for unseen task families'}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round0304GuardedAgent"]
