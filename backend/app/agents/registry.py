"""
app/agents/registry.py — Extensible Agent Registry

Provides a decorator-based registry so new agents can be added
WITHOUT modifying the core Supervisor.  Agents self-register on
import; just add the module to the supervisor imports list.

Usage
-----
    # Define a new agent:
    @agent_registry.register("web_research")
    class WebResearchAgent(BaseAgent): ...

    # Retrieve & run:
    agent = agent_registry.get("web_research")
    result = await agent.run(task_input, config)

    # List available agents:
    names = agent_registry.list_agents()
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger("agents.registry")


# ─────────────────────────────────────────────────────────────────────────────
#  Shared data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentTask:
    """Represents one unit of work dispatched to a sub-agent."""
    id: str
    agent_name: str
    input: Dict[str, Any]
    status: str = "pending"          # pending | running | done | failed | skipped
    output: Optional[Any] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 2
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_started(self) -> None:
        self.started_at = datetime.utcnow()
        self.status = "running"

    def mark_done(self, output: Any) -> None:
        self.finished_at = datetime.utcnow()
        self.output = output
        self.status = "done"
        if self.started_at:
            self.duration_ms = (self.finished_at - self.started_at).total_seconds() * 1000

    def mark_failed(self, error: str) -> None:
        self.finished_at = datetime.utcnow()
        self.error = error
        self.status = "failed"
        if self.started_at:
            self.duration_ms = (self.finished_at - self.started_at).total_seconds() * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "retries": self.retries,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "metadata": self.metadata,
        }


@dataclass
class AgentResult:
    """Standardized return value from every sub-agent."""
    agent_name: str
    success: bool
    content: str = ""                # Primary text output
    artifacts: List[Dict] = field(default_factory=list)   # Produced files/data
    sources: List[Dict] = field(default_factory=list)     # Web/doc citations
    code_output: Optional[str] = None
    error: Optional[str] = None
    quality_score: float = 1.0       # Set by Critic agent (0.0–1.0)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "success": self.success,
            "content": self.content,
            "artifacts": self.artifacts,
            "sources": self.sources,
            "code_output": self.code_output,
            "error": self.error,
            "quality_score": self.quality_score,
            "metadata": self.metadata,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Abstract Base Agent
# ─────────────────────────────────────────────────────────────────────────────

class BaseAgent(abc.ABC):
    """
    Abstract base class for all sub-agents.

    Sub-classes must implement:
      - name (class attribute)
      - description (class attribute)
      - run(task_input, config) -> AgentResult

    Optional overrides:
      - can_handle(intent) -> bool   (default: always True)
      - get_capabilities() -> list   (for Planner agent selection)
    """

    name: str = "base"
    description: str = "Base agent"
    capabilities: List[str] = []

    @abc.abstractmethod
    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """Execute the agent's core task. Must be async."""
        ...

    def can_handle(self, intent: str) -> bool:
        """Override to restrict which intents this agent handles."""
        return True

    def get_capabilities(self) -> List[str]:
        """Return a list of capability strings for Planner routing."""
        return self.capabilities or [self.name]

    def __repr__(self) -> str:
        return f"<Agent name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
#  Agent Registry Singleton
# ─────────────────────────────────────────────────────────────────────────────

class AgentRegistry:
    """
    Global registry mapping agent name → agent instance.

    Thread-safe read; write only happens at startup during module imports.
    Agents are registered once via @agent_registry.register("name").
    """

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, name: str):
        """
        Class decorator that registers an agent under `name`.

        @agent_registry.register("web_research")
        class WebResearchAgent(BaseAgent): ...
        """
        def decorator(agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
            instance = agent_class()
            self._agents[name] = instance
            logger.info(f"[AgentRegistry] Registered agent: '{name}' ({agent_class.__name__})")
            return agent_class
        return decorator

    def get(self, name: str) -> BaseAgent:
        """Retrieve an agent by name. Raises KeyError if not found."""
        if name not in self._agents:
            available = list(self._agents.keys())
            raise KeyError(
                f"Agent '{name}' not found. Available agents: {available}"
            )
        return self._agents[name]

    def list_agents(self) -> List[str]:
        """Return sorted list of all registered agent names."""
        return sorted(self._agents.keys())

    def get_all(self) -> Dict[str, BaseAgent]:
        """Return a shallow copy of the registry dict."""
        return dict(self._agents)

    def capabilities_map(self) -> Dict[str, List[str]]:
        """Return {agent_name: [capability, ...]} for Planner use."""
        return {
            name: agent.get_capabilities()
            for name, agent in self._agents.items()
        }

    def describe_all(self) -> List[Dict[str, Any]]:
        """Return agent metadata list for API and Planner prompts."""
        return [
            {
                "name": name,
                "description": agent.description,
                "capabilities": agent.get_capabilities(),
            }
            for name, agent in self._agents.items()
        ]


# Module-level singleton — import this everywhere
agent_registry = AgentRegistry()
