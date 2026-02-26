"""
Query engine: retrieve context + synthesize response.

Combines a Retriever with response synthesis for RAG-style Q&A.
"""

from __future__ import annotations

from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.indexing.base import BaseRetriever
from structure_d.indexing.documents import Node

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

    Usage::

        retriever = index.as_retriever(top_k=5)
        engine = QueryEngine(retriever=retriever, llm_client=client)
        answer = await engine.query("What is the total amount?", model="llama-3.1-8b")
    """

    def __init__(
        self,
        retriever: BaseRetriever,
        llm_client: Any = None,
        response_mode: str = "simple",
        top_k: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm_client = llm_client
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

        If no llm_client was provided at construction, returns formatted context only.
        """
        k = top_k if top_k is not None else self.top_k
        nodes = await self.retriever.retrieve(question, top_k=k)
        context = self.synthesizer.format_context(nodes)

        if system_prompt is None:
            system_prompt = self.synthesizer.system_prompt
        sys_content = system_prompt.format(context=context or "(No relevant context found.)")

        if self.llm_client is None:
            return f"Context:\n{context}\n\nQuestion: {question}\n(No LLM configured; set llm_client for full RAG.)"

        settings = get_settings()
        model_name = model or settings.models.default_model
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": question},
        ]
        response = await self.llm_client.chat(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choices = response.get("choices", [])
        return choices[0].get("message", {}).get("content", "") if choices else ""
