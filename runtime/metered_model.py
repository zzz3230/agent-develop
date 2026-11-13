"""openJiuwen Model with the contest's cost accounting on every request."""
from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig

from runtime.budget import Budget


# 429 included: the proxy limits concurrent requests per account ("Слишком много одновременных
# запросов"); without a retry four rate-limited calls in a row ended the whole run.
TRANSIENT = re.compile(r'\b50[0234]\b|\b429\b|RateLimit|Too Many Requests|Слишком много|InternalServerError|'
                       r'ServiceUnavailable|Bad Gateway|Timeout|timed out|Connection(Error| reset| refused)|'
                       r'APIConnectionError', re.I)
RETRY_DELAYS = (2.0, 5.0, 10.0, 30.0)  # a failed request is not billed, so retrying is free


def _estimate_tokens(value: Any) -> int:
    return len(str(value)) // 4 + 1


class MeteredModel(Model):
    """A gap OJ does not cover: input/10 + output summed across all tasks of a run."""

    def __init__(self, client: ModelClientConfig, request: ModelRequestConfig, budget: Budget):
        super().__init__(client, request)
        self._budget = budget
        self._name = request.model_name

    def _charge(self, messages: Any, tools: Any, message: Any) -> None:
        usage = getattr(message, "usage_metadata", None)
        reported_in = int(getattr(usage, "input_tokens", 0) or 0)
        reported_out = int(getattr(usage, "output_tokens", 0) or 0)
        calls = "".join(
            f"{getattr(call, 'name', '')}{getattr(call, 'arguments', '')}"
            for call in getattr(message, "tool_calls", None) or []
        )
        # Some servers leave reasoning out of completion_tokens; a request with
        # lost usage is estimated rather than treated as free.
        produced = _estimate_tokens(
            f"{getattr(message, 'content', '') or ''}"
            f"{getattr(message, 'reasoning_content', '') or ''}{calls}"
        )
        estimated = reported_in == 0 or reported_out == 0
        input_tokens = reported_in or _estimate_tokens(f"{messages}{tools}")
        self._budget.charge(self._name, input_tokens, max(reported_out, produced), estimated)

    async def invoke(self, messages: Any, *, tools: Any = None, **kwargs: Any) -> Any:
        for delay in (*RETRY_DELAYS, None):
            self._budget.check()
            try:
                message = await super().invoke(messages, tools=tools, **kwargs)
                break
            except Exception as exc:
                if delay is None or not TRANSIENT.search(f'{type(exc).__name__}: {exc}'):
                    raise
                self._budget.journal.write('llm_retry', task=self._budget.task_id, error=str(exc)[:200], delay=delay)
                await asyncio.sleep(delay)
        self._charge(messages, tools, message)
        return message

    async def stream(self, messages: Any, *, tools: Any = None, **kwargs: Any) -> AsyncIterator[Any]:
        self._budget.check()
        final = None
        async for chunk in super().stream(messages, tools=tools, **kwargs):
            final = chunk if final is None else final + chunk
            yield chunk
        if final is not None:
            self._charge(messages, tools, final)
