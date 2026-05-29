import textwrap
import json
from typing import Any, Callable, Dict, List, Optional
from jinja2 import StrictUndefined, Template

from Agents.memory import ActionStep, AgentMemory, PlanningStep, SummaryStep
from Agents.models import ChatMessage, MessageRole
from Agents.monitoring import AgentLogger, LogLevel
from Agents.tools import Tool
from rich.rule import Rule
from rich.text import Text
from .base_planning import BasePlanning

def populate_template(template: str, variables: Dict[str, Any]) -> str:
    compiled_template = Template(template, undefined=StrictUndefined)
    try:
        return compiled_template.render(**variables)
    except Exception as e:
        raise Exception(f"Error during jinja template rendering: {type(e).__name__}: {e}")

class FlowSearcherPlanning(BasePlanning):
    def __init__(self, model, tools, prompt_templates, memory, logger):
        super().__init__(model, tools, prompt_templates, memory, logger)

    def _get_agent(self):
        for tool in self.tools.values():
            if hasattr(tool, "agent"): return tool.agent
        return None

    def topology_initialize(self, task: str) -> PlanningStep:
        self.logger.log(Rule("[bold]Decomposing Task into Flow Graph", style="cyan"), level=LogLevel.INFO)
        
        agent = self._get_agent()
        if not agent:
            return PlanningStep(model_input_messages=[], plan="Agent reference not found.", plan_think="", plan_reasoning="Failed.")

        # Step 0.1: Initialize with Answer Node n1
        agent.knowledge_graph = {
            "nodes": {
                "n1": {
                    "node_id": "n1",
                    "type": "answer",
                    "task": task,
                    "status": "pending",
                    "context": ""
                }
            },
            "edges": []
        }
        
        # Step 0.2: Call Model to Expand Graph from n2 onwards
        current_graph_str = json.dumps(agent.knowledge_graph, indent=2, ensure_ascii=False)
        system_prompt = populate_template(
            self.prompt_templates["planning"]["initial_plan"],
            variables={"task": task, "current_graph": current_graph_str}
        )
        input_messages = [{"role": MessageRole.SYSTEM, "content": [{"type": "text", "text": system_prompt}]}]
        memory_guidance = self.append_memory_guidance(input_messages)
        
        chat_message_plan: ChatMessage = self.model(input_messages)
        content = chat_message_plan.content
        
        json_content = content
        if "```json" in content:
            json_content = content.split("```json")[1].split("```")[0].strip()
        elif "{" in content:
            json_content = content[content.find("{"):content.rfind("}")+1]
        
        try:
            graph_data = json.loads(json_content)
            # Merge expanded nodes and edges
            for node in graph_data.get("nodes", []):
                nid = node.get("node_id") or node.get("id")
                if not nid: continue
                
                task_type = node.get("type") or node.get("task_type") or "search"
                task_text = node.get("task") or node.get("content") or node.get("description")
                
                if task_type not in ["search", "solve", "answer"]: task_type = "search"

                # Update or Add node
                agent.knowledge_graph["nodes"][nid] = {
                    "node_id": nid,
                    "type": task_type,      # ti
                    "task": task_text,      # di
                    "status": "pending",    # si
                    "context": ""           # ci
                }
            
            for edge in graph_data.get("edges", []):
                s, t = edge.get("source") or edge.get("from"), edge.get("target") or edge.get("to")
                if s and t:
                    if [str(s), str(t)] not in agent.knowledge_graph["edges"]:
                        agent.knowledge_graph["edges"].append([str(s), str(t)])
                        
        except Exception as e:
            self.logger.log(f"Graph expansion failed: {e}", level=LogLevel.ERROR)

        # Step 0.3: Readable Output (Final Presentation)
        readable_plan = "### Knowledge Flow Graph Construction Summary:\n"
        readable_plan += "1. Initialized target 'answer' node n1.\n"
        readable_plan += "2. Expanded flow with sub-tasks to resolve n1.\n\n"
        
        ready_nodes = []
        readable_plan += "### Final Presentation of Nodes (v_i = [t_i, d_i, s_i, c_i]):\n"
        for nid, n in agent.knowledge_graph["nodes"].items():
            readable_plan += f"Node {nid}: ti={n['type']}, di={n['task']}, si={n['status']}, ci={n['context']}\n"
            # Calculate initial ready nodes
            deps = [e[0] for e in agent.knowledge_graph["edges"] if e[1] == nid]
            if not deps:
                ready_nodes.append({
                    "node_id": nid, "ti": n['type'], "di": n['task'], "si": n['status'], "ci": n['context']
                })
        
        readable_plan += "\n### Final Presentation of Edges (e_ij):\n"
        for e in agent.knowledge_graph["edges"]:
            readable_plan += f"Edge: {e[0]} -> {e[1]}\n"
        
        readable_plan += f"\n\n### INITIAL READY NODES:\n{json.dumps(ready_nodes, indent=2, ensure_ascii=False)}"
        self.logger.log(Text(readable_plan, style="green"), level=LogLevel.INFO)
        
        planning_step = PlanningStep(
            model_input_messages=input_messages,
            plan=readable_plan,
            plan_think=chat_message_plan.reasoning_content or "",
            plan_reasoning="Graph decomposition and expansion complete.",
            memory_guidance=memory_guidance,
        )
        self.memory.steps.append(planning_step)
        return planning_step

    def adaptation(self, task, step, write_memory_to_messages) -> SummaryStep:
        agent = self._get_agent()
        graph_status = json.dumps(agent.knowledge_graph, indent=2, ensure_ascii=False) if agent and hasattr(agent, "knowledge_graph") else "{}"
        
        refine_instruction = textwrap.dedent(f"""
            Current Knowledge Flow Graph Status:
            {graph_status}
            
            Analyze progress. Your response MUST be a JSON tool call:
            - Call `Executor(node_id, ti, di, si, ci)` for ready nodes.
            - Call `Refine(...)` to update results and structure.
            - Call `final_answer` if complete.
        """)
        
        input_messages = write_memory_to_messages(None, False)
        input_messages.append({"role": MessageRole.USER, "content": [{"type": "text", "text": refine_instruction}]})
        
        chat_message_summary: ChatMessage = self.model(input_messages)
        summary_step = SummaryStep(model_input_messages=input_messages, summary=chat_message_summary.content, summary_reasoning=chat_message_summary.reasoning_content or "")
        self.memory.steps.append(summary_step)
        return summary_step

