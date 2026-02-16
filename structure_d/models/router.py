"""Task-based model routing."""

from __future__ import annotations

import structlog

from structure_d.models.registry import ModelEntry, ModelRegistry
from structure_d.schemas.base import TaskType

logger = structlog.get_logger(__name__)


class ModelRouter:
    """
    Select the best model for a given task based on registry metadata,
    input characteristics and resource constraints.
    """

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def route(
        self,
        task: TaskType,
        *,
        input_tokens: int = 0,
        domain: str | None = None,
        prefer_multimodal: bool = False,
        max_cost_per_1k: float | None = None,
        max_size_b: float | None = None,
    ) -> ModelEntry:
        """
        Pick a model for *task*, optionally filtering by constraints.

        Parameters
        ----------
        task:
            The extraction task type.
        input_tokens:
            Approximate token count of the input (used for context-window fit).
        domain:
            Optional domain hint (e.g. "finance", "medical").
        prefer_multimodal:
            If True, prefer vision-language models.
        max_cost_per_1k:
            Upper cost bound.
        max_size_b:
            Upper model-size bound (billions of params).
        """
        candidates = self.registry.get_by_task(task)

        if domain:
            domain_specific = [c for c in candidates if c.domain == domain]
            if domain_specific:
                candidates = domain_specific

        if prefer_multimodal:
            mm = [c for c in candidates if c.multimodal]
            if mm:
                candidates = mm

        # Filter by context window
        if input_tokens > 0:
            candidates = [c for c in candidates if c.max_context >= input_tokens]

        # Filter by cost
        if max_cost_per_1k is not None:
            candidates = [c for c in candidates if c.cost_per_1k_tokens <= max_cost_per_1k]

        # Filter by model size
        if max_size_b is not None:
            candidates = [c for c in candidates if c.size_b <= max_size_b]

        if not candidates:
            # Fall back to the registry's default for the task
            default = self.registry.get_default_for_task(task)
            if default is None:
                raise ValueError(
                    f"No suitable model found for task={task.value} with the given constraints."
                )
            logger.warning(
                "model_router_fallback",
                task=task.value,
                model=default.alias or default.name,
            )
            return default

        # Return cheapest among remaining candidates
        chosen = candidates[0]
        logger.info(
            "model_routed",
            task=task.value,
            model=chosen.alias or chosen.name,
            cost=chosen.cost_per_1k_tokens,
        )
        return chosen
