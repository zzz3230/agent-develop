"""Builds openJiuwen's own agents with its stock tools; no custom loop or tools."""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any

from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
from openjiuwen.core.foundation.tool import Tool
from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
from openjiuwen.core.sys_operation import LocalWorkConfig, OperationMode, SysOperationCard
from openjiuwen.core.sys_operation.cwd import set_cwd
from openjiuwen.harness.factory import create_deep_agent
from openjiuwen.harness.rails.sys_operation_rail import SysOperationRail
from openjiuwen.harness.tools import BashTool, EditFileTool, GrepTool, ListDirTool, ReadFileTool, WriteFileTool

from runtime.budget import Budget
from runtime.metered_model import MeteredModel
from runtime.profiles import BASELINE_SYSTEM

SYSTEM = BASELINE_SYSTEM
SHELL_ALLOWLIST = ["python3", "python", "ls", "cat", "grep", "head", "tail", "wc", "sort", "cut", "find", "echo", "pwd"]
STOCK_TOOLS = {
    "read": ReadFileTool, "write": WriteFileTool, "edit": EditFileTool,
    "list": ListDirTool, "grep": GrepTool, "bash": BashTool,
}
SHORT_DESCRIPTIONS = {
    "read_file": "Read a text file.",
    "write_file": "Write a whole file.",
    "edit_file": "Replace exact text in a file; read it first.",
    "list_files": "List a directory.",
    "grep": "Search files with a regex.",
    "bash": "Run a shell command.",
}


@dataclass(frozen=True)
class Connection:
    base_url: str
    api_key: str

    def client(self) -> ModelClientConfig:
        return ModelClientConfig(
            client_provider="OpenAI", api_key=self.api_key, api_base=self.base_url, timeout=120, max_retries=1,
        )


def _compact(card: Any) -> None:
    """Stock tool, shorter schema: its text is resent on every step and paid for each time."""
    card.description = SHORT_DESCRIPTIONS.get(card.name, card.description)
    schema = copy.deepcopy(card.input_params)
    for spec in (schema or {}).get("properties", {}).values():
        spec.pop("description", None)
    card.input_params = schema


def react_agent(budget: Budget, connection: Connection, model: str, cwd: str, tools: tuple[str, ...],
                max_steps: int, max_output: int, compact: bool = True,
                system_prompt: str | None = None) -> ReActAgent:
    """Per task: its own sandbox rooted at the task's directory."""
    client = connection.client()
    request = ModelRequestConfig(model=model, temperature=0.0, max_tokens=max_output)
    operation_id = f"op-{uuid.uuid4().hex}"
    Runner.resource_mgr.add_sys_operation(SysOperationCard(
        id=operation_id, mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(sandbox_root=[cwd], restrict_to_sandbox=True, shell_allowlist=SHELL_ALLOWLIST),
    ))
    operation = Runner.resource_mgr.get_sys_operation(operation_id)
    set_cwd(cwd)

    agent = ReActAgent(AgentCard(name="solver", description="solver", id=f"solver-{uuid.uuid4().hex}"))
    agent.configure(ReActAgentConfig(
        model_name=model, model_provider="OpenAI", api_key=connection.api_key, api_base=connection.base_url,
        max_iterations=max_steps, prompt_template=[{"role": "system", "content": system_prompt if system_prompt is not None else SYSTEM}],
        model_client_config=client, model_config_obj=request,
    ))
    agent.set_llm(MeteredModel(client, request, budget))
    for key in tools:
        stock: Tool = STOCK_TOOLS[key](operation, language="en", agent_id=agent.card.id)
        if compact:
            _compact(stock.card)
        Runner.resource_mgr.add_tool(stock)
        agent.ability_manager.add(stock.card)
    return agent


def deep_agent(budget: Budget, connection: Connection, model: str, workspace: str,
               max_steps: int, max_output: int) -> Any:
    """Kept for the measured comparison in docs/gaps.md; not used by run_agent."""
    llm = MeteredModel(connection.client(), ModelRequestConfig(model=model, temperature=0.0, max_tokens=max_output), budget)
    return create_deep_agent(
        llm, card=AgentCard(name="solver", description="solver", id=f"solver-{uuid.uuid4().hex}"),
        system_prompt=SYSTEM, rails=[SysOperationRail()], max_iterations=max_steps, workspace=workspace,
        language="en", restrict_to_work_dir=True, enable_security_rail=False,
        enable_model_anomaly_detection_rail=False, enable_read_image_multimodal=False, prompt_mode="minimal",
    )
