"""Legacy v1 LLM extraction layer.

.. deprecated:: 0.2.0
    Use :mod:`passport_core.extraction` instead. This module will be
    removed once upstream adapters migrate to the v2 extraction pipeline.
"""

from __future__ import annotations

import re
import warnings
from typing import Any, Protocol

from pydantic_ai import Agent, BinaryContent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from passport_core.config import Settings
from passport_core.models import PassportData

warnings.warn(
    "passport_core.llm is deprecated, use passport_core.extraction instead",
    DeprecationWarning,
    stacklevel=2,
)

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

EXTRACTION_PROMPT = """
You extract fields from a single passport image.
The image may show:
- A single passport data page
- A two-page spread (open passport booklet)
- A passport on an A4 scanned sheet with background/margins

Extract the following:
- Surname and given names (Arabic and English versions, full concatenated strings).
- Individual name slots: first name, father name, grandfather name (Arabic and English).
- Profession, place of birth, and issuing authority (Arabic and English).
- Place of birth split into city and country separately (Arabic and English).
- Date of birth, sex, date of issue, date of expiry — from English fields only.
- The 2 MRZ lines.

Rules:
- Return only factual values visible in the image.
- Do not invent or infer missing values.
- Keep Arabic fields in Arabic script exactly as seen.
- Keep English fields in uppercase as shown when possible.
- Each Arabic name token must be written as a single unspaced word when it is a compound.
  "عبدالله" is one token (not "عبد الله"), "عبدالرحمن" is one token, "عبدالحكيم" is one token, etc.
  Separate name tokens are still separated by spaces:
  "عمر عبدالحكيم حزام" has 3 tokens, each unspaced internally.
- GivenNamesAr / GivenNamesEn are the full given-names string (all tokens space-separated).
- FirstName = first given name, FatherName = second given name (father),
  GrandfatherName = third given name.
- PlaceOfBirthAr / PlaceOfBirthEn are the full place-of-birth string as printed on the passport.
- BirthCityAr / BirthCityEn are the most specific location (city or mudiriyah/district)
  without the country. e.g. "الشمايتين" not "تعز", "جده" not "السعودية - جده",
  "JEDDAH" not "JEDDAH - KSA".
- BirthCountryAr / BirthCountryEn are the country part only
  (e.g. "السعودية", "KSA" / "اليمن", "YEM").
- For dates, use strictly DD/MM/YYYY format. If uncertain, return null.
- For Sex, return only "M" or "F" when confidently visible, otherwise null.
- If a value is not visible, set it to null.

Return a JSON object with exactly these keys:
PassportNumber, CountryCode, MrzLine1, MrzLine2,
SurnameAr, GivenNamesAr, FirstNameAr, FatherNameAr, GrandfatherNameAr,
SurnameEn, GivenNamesEn, FirstNameEn, FatherNameEn, GrandfatherNameEn,
DateOfBirth, PlaceOfBirthAr, PlaceOfBirthEn,
BirthCityAr, BirthCityEn, BirthCountryAr, BirthCountryEn, Sex,
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
    """PydanticAI client using Requesty as an OpenAI-compatible router.

    Uses PromptedOutput so the model emits JSON matching PassportData schema directly,
    avoiding Gemini leaking chain-of-thought text before tool-call responses.
    """

    def __init__(self, api_key: str, model: str, base_url: str) -> None:

        self._agent = Agent(
            model=OpenAIChatModel(
                model, provider=OpenAIProvider(base_url=base_url, api_key=api_key)
            ),
            instructions=EXTRACTION_PROMPT,
            output_type=PromptedOutput(PassportData),
            retries=2,
        )

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportData:
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
