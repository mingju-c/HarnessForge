__all__ = [
    "OpenAIServerModel",
    "PureReActAgent",
    "Tool",
    "ToolCallingAgent",
]


def __getattr__(name):
    if name == "ToolCallingAgent":
        from .agents import ToolCallingAgent

        return ToolCallingAgent
    if name == "OpenAIServerModel":
        from .models import OpenAIServerModel

        return OpenAIServerModel
    if name == "Tool":
        from .tools import Tool

        return Tool
    if name == "PureReActAgent":
        from .react_agent import PureReActAgent

        return PureReActAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
