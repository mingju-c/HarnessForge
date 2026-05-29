from __future__ import annotations

from .round02_02_agent import Round0202ActionProvider, Round0202GuardedAgent


ACTION_SYSTEM = "format_contract_react"
ACTION_MODULE = "format_contract_react"


class ActionProvider(Round0202ActionProvider):
    PROMPTS_TYPE = ACTION_SYSTEM
    SUMMARY_INTERVAL = 6
    VARIANT_CONFIG = {'support_record_gate': True,
 'support_mode': 'route',
 'complete_gate': True,
 'completion_policy': 'progress',
 'drop_extra_keys': True,
 'repeat_limit': 2,
 'partial_commit_on_blocker': True,
 'min_successful_mutations_before_partial_complete': 1,
 'planned_mutation_cap': 1,
 'enable_ledger_review_tool': False,
 'date_iso_canonicalization': True,
 'narrow_alias_trim': True,
 'focus': 'task-conditioned final-answer canonicalization at commit time'}


def get_provider():
    return ActionProvider()


__all__ = ["ACTION_SYSTEM", "ACTION_MODULE", "ActionProvider", "get_provider", "Round0202GuardedAgent"]
