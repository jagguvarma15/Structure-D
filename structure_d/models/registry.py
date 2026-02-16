"""Model registry: catalogue of available models with metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from structure_d.schemas.base import TaskType


class ModelEntry(BaseModel):
    """Describes a single model available for inference."""

    name: str  # HuggingFace ID or local path
    alias: str = ""
    tasks: list[TaskType] = Field(default_factory=list)
    size_b: float = 0  # billions of parameters
    quantisation: str | None = None  # AWQ, GPTQ, etc.
    max_context: int = 4096
    cost_per_1k_tokens: float = 0.01
    supports_structured_output: bool = True
    multimodal: bool = False
    lora_adapter: str | None = None
    domain: str | None = None
    notes: str = ""


class ModelRegistry:
    """
    Maintains a list of :class:`ModelEntry` objects.

    Load from a YAML file (``configs/models.yaml``) or register
    programmatically.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelEntry] = {}
        self._task_defaults: dict[str, str] = {}

    # ── Loading ───────────────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str | Path) -> ModelRegistry:
        """Build a registry from a YAML config file."""
        registry = cls()
        p = Path(path)
        if not p.exists():
            return registry

        with open(p) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        for entry_data in data.get("models", []):
            # Convert task strings to TaskType enums
            tasks_raw = entry_data.pop("tasks", [])
            tasks = []
            for t in tasks_raw:
                try:
                    tasks.append(TaskType(t))
                except ValueError:
                    pass
            entry = ModelEntry(tasks=tasks, **entry_data)
            key = entry.alias or entry.name
            registry._models[key] = entry

        registry._task_defaults = data.get("task_defaults", {})
        return registry

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, entry: ModelEntry) -> None:
        key = entry.alias or entry.name
        self._models[key] = entry

    def unregister(self, key: str) -> None:
        self._models.pop(key, None)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, key: str) -> ModelEntry | None:
        return self._models.get(key)

    def list_models(self) -> list[ModelEntry]:
        return list(self._models.values())

    def list_aliases(self) -> list[str]:
        return list(self._models.keys())

    def get_by_task(self, task: TaskType) -> list[ModelEntry]:
        """Return all models that support *task*, sorted by cost (ascending)."""
        matches = [m for m in self._models.values() if task in m.tasks]
        return sorted(matches, key=lambda m: m.cost_per_1k_tokens)

    def get_default_for_task(self, task: TaskType) -> ModelEntry | None:
        """Return the configured default model for a task."""
        alias = self._task_defaults.get(task.value)
        if alias:
            return self._models.get(alias)
        # Fallback: cheapest model for the task
        candidates = self.get_by_task(task)
        return candidates[0] if candidates else None

    def get_multimodal(self) -> list[ModelEntry]:
        return [m for m in self._models.values() if m.multimodal]

    def get_by_domain(self, domain: str) -> list[ModelEntry]:
        return [m for m in self._models.values() if m.domain == domain]
