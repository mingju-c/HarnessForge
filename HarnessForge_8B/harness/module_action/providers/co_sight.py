from __future__ import annotations

from typing import Any

from Agents.agents import ToolCallingAgent

from module_action.base_action import ActionContext, BaseActionProvider


class CosightActionProvider(BaseActionProvider):
    def build_affordance(
        self,
        bench_type: str | None,
        context: ActionContext,
    ) -> list[Any]:
        return self.get_primary_task_tools(context, include_reasoning=True)

    def build_specification(
        self,
        context: ActionContext,
        tools: list[Any],
    ) -> None:
        self.prompts_type = context.prompts_type or "co-sight"
        self.prompt_templates = self.load_prompt_templates(context, "co-sight")
        self.organization_planning_system = context.planning_system
        self.coordinator_role = {
            "name": "CoSight Coordinator",
            "responsibility": "Coordinate expert_parallel and CAMV for final synthesis.",
        }
        self.expert_role = {
            "name": "CoSight Expert",
            "responsibility": "Conduct autonomous tool-based investigation and return grounded findings.",
        }
        expert_prompts = self.prompt_templates.get("expert_internal")
        self.experts = [
            ToolCallingAgent(
                model=context.model,
                tools=tools,
                planning_system="co-sight",
                prompt_templates=expert_prompts,
                name=f"expert_{i + 1}",
                summary_interval=context.max_steps + 1,
                description="Autonomous research expert.",
            )
            for i in range(4)
        ]
        for expert in self.experts:
            if getattr(expert, "planning", None) is not None:
                expert.planning.role_info = self.expert_role

    def build_organization(
        self,
        context: ActionContext,
        tools: list[Any],
    ):
        context.expert_parallel_tool.agents = self.experts
        root_tools = self.normalize_tools([context.expert_parallel_tool, context.camv_tool])
        agent = self.create_agent(
            context,
            tools=root_tools,
            prompt_templates=self.prompt_templates,
            prompts_type=self.prompts_type,
            planning_system=self.organization_planning_system,
        )
        if getattr(agent, "planning", None) is not None:
            agent.planning.role_info = self.coordinator_role
        agent.managed_agents = {expert.name: expert for expert in self.experts}
        context.expert_parallel_tool.set_prompt_templates(agent.prompt_templates)
        context.camv_tool.set_prompt_templates(agent.prompt_templates)
        return agent
