"""Multi-step passport extractor using PydanticAI."""

from __future__ import annotations

from dataclasses import asdict

from pydantic_ai import Agent, BinaryContent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage

from passport_core.extraction.confidence import compute_confidence
from passport_core.extraction.models import (
    AgentOutput,
    ExtractionResult,
    PassportFields,
)
from passport_core.extraction.normalize import normalize_fields, normalize_meta
from passport_core.extraction.prompt import EXTRACTION_PROMPT
from passport_core.extraction.validate import cross_validate


def _usage_dict(usage: RunUsage) -> dict[str, int]:
    """Flatten PydanticAI RunUsage into a simple {token_type: count} dict."""
    data = asdict(usage)
    total_tokens = sum(
        value for key, value in data.items() if key.endswith("_tokens") and isinstance(value, int)
    )
    details = data.pop("details", {})
    usage_data = {key: value for key, value in data.items() if isinstance(value, int)}
    usage_data["total_tokens"] = total_tokens
    for key, value in details.items():
        usage_data[f"detail_{key}"] = value
    return usage_data


class PassportExtractor:
    """Multi-step passport extractor with reasoning trace and MRZ cross-validation."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._agent = Agent(
            model=OpenAIChatModel(
                model,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
            ),
            instructions=EXTRACTION_PROMPT,
            output_type=PromptedOutput(AgentOutput),
            retries=2,
        )

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> ExtractionResult:
        """Send image to VLM, normalize output, cross-validate, and compute confidence."""
        result = self._agent.run_sync(
            [
                "Extract passport fields from this image following all 7 steps and return JSON.",
                BinaryContent(data=image_bytes, media_type=mime_type),
            ]
        )
        raw = result.output
        if not isinstance(raw, AgentOutput):
            msg = "PydanticAI did not return AgentOutput."
            raise ValueError(msg)

        data = normalize_fields(
            PassportFields.model_validate(raw.model_dump(exclude={"meta", "reasoning"}))
        )
        meta = normalize_meta(raw.meta)
        warnings = cross_validate(data.model_dump())
        usage = _usage_dict(result.usage())
        confidence = compute_confidence(data, meta, warnings)
        message_history_json = result.all_messages_json().decode("utf-8")

        return ExtractionResult(
            data=data,
            meta=meta,
            reasoning=raw.reasoning,
            confidence=confidence,
            warnings=warnings,
            usage=usage,
            message_history_json=message_history_json,
        )
