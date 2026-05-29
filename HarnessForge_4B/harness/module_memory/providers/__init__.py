"""
Memory providers for different frameworks
"""

__all__ = []


def _safe_register(class_name: str, module_name: str) -> None:
    try:
        module = __import__(f"{__name__}.{module_name}", fromlist=[class_name])
        provider_cls = getattr(module, class_name)
        globals()[class_name] = provider_cls
        __all__.append(class_name)
    except Exception:
        # Some providers depend on optional modules (e.g. storage/*).
        # Keep package import resilient and let caller import the concrete
        # provider module it needs.
        pass


_safe_register("AgentKBProvider", "agent_kb_provider")
_safe_register("SkillWeaverProvider", "skillweaver_provider")
_safe_register("MobileEProvider", "mobilee_provider")
_safe_register("ExpeLProvider", "expel_provider")
