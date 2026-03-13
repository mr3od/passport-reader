from __future__ import annotations

import re
from typing import Any, Protocol

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
    if settings.requesty_api_key is None:
        raise ValueError("Set PASSPORT_REQUESTY_API_KEY.")

    return PydanticAIRequestyExtractor(
        api_key=settings.requesty_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.requesty_base_url,
    )


def _normalize(data: PassportData) -> PassportData:
    updates: dict[str, Any] = {}
    for field_name in PassportData.model_fields:
        value = getattr(data, field_name)
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value.upper() == "NULL":
                value = None
        updates[field_name] = value

    for date_field in ("DateOfBirth", "DateOfIssue", "DateOfExpiry"):
        value = updates[date_field]
        if value is not None and not DATE_PATTERN.fullmatch(value):
            updates[date_field] = None

    updates["Sex"] = updates["Sex"] if updates["Sex"] in {"M", "F"} else None

    return data.model_copy(update=updates)


class PydanticAIRequestyExtractor:
    """PydanticAI client using Requesty OpenAI-compatible base URL.

    Structured schema output is enforced by ``output_type=PassportData``.
    """

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
        raise ValueError("PydanticAI did not return PassportData output.")
