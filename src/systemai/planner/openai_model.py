from __future__ import annotations

import asyncio
import os
from typing import Any


class OpenAIResponsesModel:
    """Optional OpenAI Responses API adapter using Structured Outputs."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("SYSTEMAI_OPENAI_MODEL", "gpt-5.6")

    async def __call__(self, prompt: str, schema: dict[str, Any]) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI extra not installed: pip install 'systemai-core[ai]'") from exc

        def run() -> str:
            client = OpenAI()
            response = client.responses.create(
                model=self.model,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "systemai_task_plan",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )
            return response.output_text

        return await asyncio.to_thread(run)
