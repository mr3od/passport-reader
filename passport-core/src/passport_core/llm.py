from __future__ import annotations

import base64
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
    if settings.llm_provider == "google":
        if settings.google_api_key is None:
            raise ValueError("PASSPORT_GOOGLE_API_KEY is required for llm_provider=google.")
        return GooglePassportExtractor(
            api_key=settings.google_api_key.get_secret_value(),
            model=_strip_prefix(settings.llm_model, "google"),
        )

    if settings.openai_api_key is None:
        raise ValueError("PASSPORT_OPENAI_API_KEY is required for llm_provider=openai_responses.")
    return OpenAIResponsesPassportExtractor(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.requesty_base_url,
    )


def _strip_prefix(value: str, prefix: str) -> str:
    marker = f"{prefix}/"
    return value[len(marker) :] if value.startswith(marker) else value


def _strict_json_schema() -> dict[str, object]:
    schema = PassportData.model_json_schema()
    schema["additionalProperties"] = False
    schema["required"] = list(PassportData.model_fields.keys())
    return schema


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


class GooglePassportExtractor:
    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportData:
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                EXTRACTION_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=PassportData,
            ),
        )

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return _normalize(PassportData.model_validate(parsed))

        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Google response did not contain JSON text.")
        return _parse_json_text(text)


class OpenAIResponsesPassportExtractor:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportData:
        encoded = base64.b64encode(image_bytes).decode("ascii")

        response = self.client.responses.create(
            model=self.model,
            temperature=0,
            max_output_tokens=1200,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": EXTRACTION_PROMPT},
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{encoded}",
                            "detail": "high",
                        },
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "passport_extraction",
                    "schema": _strict_json_schema(),
                    "strict": True,
                }
            },
        )

        text = getattr(response, "output_text", None) or self._collect_output_text(response)
        if not text:
            raise ValueError("OpenAI Responses output did not contain JSON text.")
        return _parse_json_text(text)

    def _collect_output_text(self, response: object) -> str:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                fragment = getattr(content, "text", None)
                if fragment:
                    parts.append(fragment)
        return "".join(parts)
