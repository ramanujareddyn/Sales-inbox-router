import json
import time
import httpx
from .config import GEMINI_API_KEY, GEMINI_MODEL

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)


class GeminiError(Exception):
    pass


def _extract_text(resp_json: dict) -> str:
    try:
        return resp_json["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise GeminiError(f"Unexpected Gemini response shape: {resp_json}")


def call_gemini_json(system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
    """
    Calls Gemini with response_mime_type=application/json so the model is constrained
    to emit valid JSON, and retries with exponential backoff on 429/5xx/timeouts.
    Raises GeminiError if all retries are exhausted — callers must handle this
    (graceful degradation, e.g. falling back to rule-based classification) rather
    than letting a single flaky call drop an email silently.
    """
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not set")

    url = GEMINI_URL.format(model=GEMINI_MODEL, key=GEMINI_API_KEY)
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }

    last_err = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(url, json=body)
            if r.status_code == 429 or r.status_code >= 500:
                raise GeminiError(f"Gemini transient error {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            text = _extract_text(r.json())
            return json.loads(text)
        except (httpx.RequestError, GeminiError, json.JSONDecodeError, httpx.HTTPStatusError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(min(2 ** attempt, 8))
            continue
    raise GeminiError(f"Gemini call failed after {max_retries} attempts: {last_err}")


def call_gemini_text(prompt: str, max_retries: int = 3) -> str:
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not set")
    url = GEMINI_URL.format(model=GEMINI_MODEL, key=GEMINI_API_KEY)
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}}
    last_err = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(url, json=body)
            if r.status_code == 429 or r.status_code >= 500:
                raise GeminiError(f"Gemini transient error {r.status_code}")
            r.raise_for_status()
            return _extract_text(r.json())
        except (httpx.RequestError, GeminiError, httpx.HTTPStatusError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(min(2 ** attempt, 8))
            continue
    raise GeminiError(f"Gemini call failed after {max_retries} attempts: {last_err}")
