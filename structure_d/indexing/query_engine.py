"""
Query engine: retrieve context + synthesize response.

Combines a Retriever with response synthesis for RAG-style Q&A.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from structure_d.config import get_settings
from structure_d.indexing.base import BaseRetriever
from structure_d.indexing.documents import Node

if TYPE_CHECKING:
    from structure_d.inference.providers import BaseLLMProvider

logger = structlog.get_logger(__name__)

_DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant. Use the context below to answer the user's question.
If the answer is not in the context, say so.

## Context
{context}
"""


def _format_context_simple(nodes: list[Node], separator: str = "\n\n---\n\n") -> str:
    """Format node texts into a single context string."""
    return separator.join(n.text for n in nodes if n.text.strip())


def _format_context_compact(
    nodes: list[Node],
    max_chars: int = 4000,
    separator: str = "\n\n---\n\n",
) -> str:
    """Concatenate node texts up to a character limit (compact mode)."""
    parts: list[str] = []
    total = 0
    for n in nodes:
        if not n.text.strip():
            continue
        if total + len(n.text) + len(separator) > max_chars:
            break
        parts.append(n.text)
        total += len(n.text) + len(separator)
    return separator.join(parts)


class ResponseSynthesizer:
    """Format retrieved context and optionally call LLM."""

    def __init__(
        self,
        response_mode: str = "simple",
        max_context_chars: int = 4000,
        system_prompt: str | None = None,
    ) -> None:
        self.response_mode = response_mode
        self.max_context_chars = max_context_chars
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    def format_context(self, nodes: list[Node]) -> str:
        if self.response_mode == "compact":
            return _format_context_compact(nodes, max_chars=self.max_context_chars)
        return _format_context_simple(nodes)


class QueryEngine:
    """
    RAG query engine: retrieve nodes, format context, generate answer.

    Accepts any :class:`~structure_d.inference.providers.BaseLLMProvider` for
    free-text answer generation via :meth:`BaseLLMProvider.generate_text`.

    Usage::

        retriever = index.as_retriever(top_k=5)
        engine = QueryEngine(retriever=retriever, provider=OpenAIProvider())
        answer = await engine.query("What is the total amount?")
    """

    def __init__(
        self,
        retriever: BaseRetriever,
        provider: BaseLLMProvider | None = None,
        response_mode: str = "simple",
        top_k: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        self.retriever = retriever
        self.provider = provider
        self.synthesizer = ResponseSynthesizer(
            response_mode=response_mode,
            system_prompt=system_prompt,
        )
        self.top_k = top_k

    async def retrieve(self, query: str, top_k: int | None = None) -> list[Node]:
        """Retrieve relevant nodes (no LLM call)."""
        k = top_k if top_k is not None else self.top_k
        return await self.retriever.retrieve(query, top_k=k)

    async def query(
        self,
        question: str,
        model: str | None = None,
        *,
        top_k: int | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
    ) -> str:
        """
        Run full RAG: retrieve context, compose prompt, generate answer.

        If no *provider* was supplied at construction, returns the formatted
        context string so callers can inspect retrieved content without needing
        an LLM.
        """
        k = top_k if top_k is not None else self.top_k
        nodes = await self.retriever.retrieve(question, top_k=k)
        context = self.synthesizer.format_context(nodes)

        sys_template = system_prompt or self.synthesizer.system_prompt
        sys_content = sys_template.format(context=context or "(No relevant context found.)")

        if self.provider is None:
            return (
                f"Context:\n{context}\n\nQuestion: {question}\n"
                "(No provider configured; pass provider= to QueryEngine for full RAG.)"
            )

        settings = get_settings()
        model_name = model or settings.models.default_model

        return await self.provider.generate_text(
            prompt=question,
            system_prompt=sys_content,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model_name,
        )
