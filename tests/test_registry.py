"""Tests for model registry and router."""

from structure_d.models.registry import ModelEntry, ModelRegistry
from structure_d.models.router import ModelRouter
from structure_d.schemas.base import TaskType


def _build_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry.register(
        ModelEntry(
            name="small-model",
            alias="small",
            tasks=[TaskType.CLASSIFICATION, TaskType.SENTIMENT],
            size_b=1.5,
            cost_per_1k_tokens=0.001,
            max_context=4096,
        )
    )
    registry.register(
        ModelEntry(
            name="medium-model",
            alias="medium",
            tasks=[TaskType.EXTRACTION, TaskType.SUMMARISATION],
            size_b=8,
            cost_per_1k_tokens=0.01,
            max_context=8192,
        )
    )
    registry.register(
        ModelEntry(
            name="large-model",
            alias="large",
            tasks=[TaskType.EXTRACTION, TaskType.REASONING],
            size_b=70,
            cost_per_1k_tokens=0.06,
            max_context=16384,
        )
    )
    return registry


def test_get_by_task():
    registry = _build_registry()
    extraction_models = registry.get_by_task(TaskType.EXTRACTION)
    assert len(extraction_models) == 2
    # Should be sorted by cost
    assert extraction_models[0].cost_per_1k_tokens <= extraction_models[1].cost_per_1k_tokens


def test_router_picks_cheapest():
    registry = _build_registry()
    router = ModelRouter(registry)
    model = router.route(TaskType.EXTRACTION)
    assert model.alias == "medium"  # cheapest extraction model


def test_router_with_size_constraint():
    registry = _build_registry()
    router = ModelRouter(registry)
    model = router.route(TaskType.EXTRACTION, max_size_b=10)
    assert model.size_b <= 10


def test_router_with_cost_constraint():
    registry = _build_registry()
    router = ModelRouter(registry)
    model = router.route(TaskType.EXTRACTION, max_cost_per_1k=0.02)
    assert model.cost_per_1k_tokens <= 0.02
