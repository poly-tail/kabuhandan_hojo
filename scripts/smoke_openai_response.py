"""Run one minimal OpenAI Responses API smoke check without FastAPI or a browser."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ai.presets import STANDARD_PRESET  # noqa: E402
from app.ai.runtime import AI_ANALYSIS_MODEL  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.integrations.openai_responses import OpenAIClientError, OpenAIResponsesClient  # noqa: E402


SMOKE_INPUT = "OpenAI Responses APIの疎通確認です。『疎通確認成功』とだけ日本語で回答してください。"
SMOKE_INSTRUCTIONS = "短い疎通確認へ指示どおりに回答してください。"


async def _run_smoke_check() -> int:
    settings = get_settings()
    client = OpenAIResponsesClient(api_key=settings.openai_api_key)

    try:
        response = await client.create_text(
            instructions=SMOKE_INSTRUCTIONS,
            input_text=SMOKE_INPUT,
            preset=STANDARD_PRESET,
        )
    except OpenAIClientError as exc:
        print(
            json.dumps(
                {
                    "api_success": False,
                    "model": AI_ANALYSIS_MODEL,
                    "preset": STANDARD_PRESET.preset_id.value,
                    "error_code": exc.code.value,
                    "error_message": exc.user_message,
                    "exception_type": exc.exception_type,
                    "http_status": exc.status_code,
                    "openai_request_id": exc.request_id,
                    "response_status": exc.response_status,
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "api_success": True,
                "model": AI_ANALYSIS_MODEL,
                "preset": STANDARD_PRESET.preset_id.value,
                "response_id": response.response_id,
                "response_status": response.status,
                "output_text_non_empty": bool(response.output_text),
                "output_text_characters": len(response.output_text),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    """Run the smoke check and return a process exit code."""

    return asyncio.run(_run_smoke_check())


if __name__ == "__main__":
    raise SystemExit(main())
