"""LLM call trace collector for live E2E tests.

Wraps BaseLLM methods to capture the full input (system prompt + messages)
and output for every LLM call during a test, then prints a structured report.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from app.llm.base import BaseLLM, LLMMessage


class LLMTraceCollector:
    """Collects all LLM calls and their inputs/outputs."""

    def __init__(self) -> None:
        self.calls: list[LLMCallRecord] = []

    def wrap(self, llm: BaseLLM, role: str = "") -> BaseLLM:
        """Wrap an LLM instance to trace all calls.

        Returns the same LLM instance with monkey-patched chat/chat_stream_parts.
        """
        collector = self
        original_chat = llm.chat
        original_stream = llm.chat_stream_parts

        async def traced_chat(
            messages: list[LLMMessage],
            system: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.3,
        ):
            rec = LLMCallRecord(
                role=role,
                model=getattr(llm.config, "model", None) or "",
                method="chat",
                system_prompt=system or "",
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            t0 = time.monotonic()
            try:
                resp = await original_chat(
                    messages, system=system, max_tokens=max_tokens, temperature=temperature
                )
                rec.duration_s = time.monotonic() - t0
                rec.output = resp.content
                rec.reasoning = resp.reasoning
                rec.input_tokens = resp.input_tokens
                rec.output_tokens = resp.output_tokens
                return resp
            except Exception as exc:
                rec.duration_s = time.monotonic() - t0
                rec.error = str(exc)
                raise
            finally:
                collector.calls.append(rec)

        async def traced_stream(
            messages: list[LLMMessage],
            system: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.3,
            *,
            use_reasoning: bool = False,
        ) -> AsyncIterator[tuple[str, Any]]:
            rec = LLMCallRecord(
                role=role,
                model=getattr(llm.config, "model", None) or "",
                method="chat_stream_parts",
                system_prompt=system or "",
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
                use_reasoning=use_reasoning,
            )
            t0 = time.monotonic()
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            try:
                async for kind, piece in original_stream(
                    messages,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    use_reasoning=use_reasoning,
                ):
                    if kind == "content" and piece:
                        content_parts.append(piece)
                    elif kind == "reasoning" and piece:
                        reasoning_parts.append(piece)
                    yield (kind, piece)
            except Exception as exc:
                rec.error = str(exc)
                raise
            finally:
                rec.duration_s = time.monotonic() - t0
                rec.output = "".join(content_parts)
                rec.reasoning = "".join(reasoning_parts)
                collector.calls.append(rec)

        llm.chat = traced_chat  # type: ignore[assignment]
        llm.chat_stream_parts = traced_stream  # type: ignore[assignment]
        return llm

    def format_report(self) -> str:
        """Format a human-readable report of all LLM calls."""
        if not self.calls:
            return "No LLM calls recorded."

        lines: list[str] = []
        lines.append("=" * 80)
        lines.append(f"LLM TRACE REPORT ({len(self.calls)} calls)")
        lines.append("=" * 80)

        for i, rec in enumerate(self.calls, 1):
            lines.append("")
            lines.append(f"--- CALL #{i} [{rec.role}] {rec.method} ---")
            lines.append(f"  Model:        {rec.model or '(unknown)'}")
            lines.append(f"  Duration:     {rec.duration_s:.2f}s")
            if rec.input_tokens:
                lines.append(f"  Input tokens: {rec.input_tokens}")
            if rec.output_tokens:
                lines.append(f"  Output tokens: {rec.output_tokens}")
            if rec.error:
                lines.append(f"  ERROR: {rec.error}")
            lines.append("")

            if rec.system_prompt:
                lines.append("  [SYSTEM PROMPT]")
                lines.append(_indent(rec.system_prompt, 4))
                lines.append("")

            lines.append("  [MESSAGES]")
            for msg in rec.messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                lines.append(f"    [{role}]")
                lines.append(_indent(content[:2000], 6))
                lines.append("")

            if rec.reasoning:
                lines.append("  [REASONING]")
                lines.append(_indent(rec.reasoning[:2000], 4))
                lines.append("")

            if rec.output:
                lines.append("  [OUTPUT]")
                lines.append(_indent(rec.output[:3000], 4))
                lines.append("")

        lines.append("=" * 80)
        total_s = sum(c.duration_s or 0 for c in self.calls)
        lines.append(f"Total LLM time: {total_s:.1f}s across {len(self.calls)} calls")
        lines.append("=" * 80)
        return "\n".join(lines)


class LLMCallRecord:
    __slots__ = (
        "role", "model", "method", "system_prompt", "messages",
        "max_tokens", "temperature", "use_reasoning",
        "output", "reasoning", "error", "duration_s",
        "input_tokens", "output_tokens",
    )

    def __init__(
        self,
        *,
        role: str = "",
        model: str = "",
        method: str = "",
        system_prompt: str = "",
        messages: list[dict[str, str]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        use_reasoning: bool = False,
    ) -> None:
        self.role = role
        self.model = model
        self.method = method
        self.system_prompt = system_prompt
        self.messages = messages or []
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.use_reasoning = use_reasoning
        self.output: str = ""
        self.reasoning: str = ""
        self.error: str = ""
        self.duration_s: float = 0.0
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())
