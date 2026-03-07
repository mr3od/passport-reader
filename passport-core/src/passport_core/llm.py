from __future__ import annotations

import json
import re
from typing import Protocol

from passport_core.config import Settings
from passport_core.models import PassportData

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

EXTRACTION_PROMPT = """
You extract fields from a single passport image.
The image may show:
- A single passport data page
- A two-page spread (open passport booklet)
- A passport on an A4 scanned sheet with background/margins

- Extract surname, given names, profession, place of birth, and issuing authority
  the arabic and english versions.
- Extract date of birth, sex, date of issue and date of expiry from english fields only.
- Extract the 2 MRZ lines.
Rules:
- Return only factual values visible in the image.
- Do not invent or infer missing values.
- Keep Arabic fields in Arabic script exactly as seen.
- Keep English fields in uppercase as shown when possible.
- For dates, use strictly DD/MM/YYYY format. If uncertain, return null.
- For Sex, return only "M" or "F" when confidently visible, otherwise null.
- Return strict JSON object only. No markdown. No extra keys.
- If a value is not visible, set it to null.

Return a JSON object with exactly these keys:
PassportNumber, CountryCode, MrzLine1, MrzLine2,
SurnameAr, GivenNamesAr, SurnameEn, GivenNamesEn,
DateOfBirth, PlaceOfBirthAr, PlaceOfBirthEn, Sex,
DateOfIssue, DateOfExpiry, ProfessionAr, ProfessionEn,
IssuingAuthorityAr, IssuingAuthorityEn
""".strip()


class PassportExtractor(Protocol):
    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportData: ...


def build_extractor(settings: Settings) -> PassportExtractor:
    api_key = _resolve_requesty_api_key(settings)
    return PydanticAIRequestyExtractor(
        api_key=api_key,
        model=settings.llm_model,
        base_url=settings.requesty_base_url,
    )


def _resolve_requesty_api_key(settings: Settings) -> str:
    # Requesty API key is preferred, with compatibility fallback to old key vars.
    if settings.requesty_api_key is not None:
        return settings.requesty_api_key.get_secret_value()

    if settings.openai_api_key is not None:
        return settings.openai_api_key.get_secret_value()

    if settings.google_api_key is not None:
        return settings.google_api_key.get_secret_value()

    raise ValueError(
        "Set PASSPORT_REQUESTY_API_KEY (or legacy PASSPORT_OPENAI_API_KEY/PASSPORT_GOOGLE_API_KEY)."
    )


def _normalize(data: PassportData) -> PassportData:
    for field_name in PassportData.model_fields:
        value = getattr(data, field_name)
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value.upper() == "NULL":
                value = None
            setattr(data, field_name, value)

    for date_field in ("DateOfBirth", "DateOfIssue", "DateOfExpiry"):
        value = getattr(data, date_field)
        if value is not None and not DATE_PATTERN.fullmatch(value):
            setattr(data, date_field, None)

    if data.Sex not in {"M", "F"}:
        data.Sex = None

    return data


def _parse_json_text(text: str) -> PassportData:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc
    return _normalize(PassportData.model_validate(payload))


class PydanticAIRequestyExtractor:
    """PydanticAI client using Requesty OpenAI-compatible base URL."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        self._agent = Agent(
            model=OpenAIChatModel(
                model,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
            ),
            instructions=EXTRACTION_PROMPT,
            output_type=PassportData,
            retries=1,
        )

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportData:
        from pydantic_ai import BinaryContent

        result = self._agent.run_sync(
            [
                "Extract passport fields from this image.",
                BinaryContent(data=image_bytes, media_type=mime_type),
            ]
        )

        output = result.output
        if isinstance(output, PassportData):
            return _normalize(output)

        if isinstance(output, str):
            return _parse_json_text(output)

        return _normalize(PassportData.model_validate(output))
