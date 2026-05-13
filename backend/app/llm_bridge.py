import json
import logging
import os
import re
import time
import requests

def _extract_json_payload(text: str):
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    for candidate in (raw,):
        try:
            return json.loads(candidate)
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return None


def _should_retry_http_error(error: Exception) -> bool:
    if isinstance(error, requests.HTTPError):
        status = error.response.status_code if error.response is not None else None
        return status in {429, 500, 502, 503, 504}
    if isinstance(error, requests.RequestException):
        return True

    text = str(error).lower()
    return any(token in text for token in ["429", "timed out", "connection", "temporary"])


def _call_openai_compatible_json(
    endpoint: str,
    payload: dict,
    headers: dict | None = None,
    timeout: int = 45,
    max_attempts: int = 2,
    backoff_seconds: float = 0.8,
):
    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            response = requests.post(endpoint, json=payload, headers=headers or {}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _extract_json_payload(content)
        except Exception as error:
            logging.exception(error)
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            time.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return None


def _call_openai_compatible_text(
    endpoint: str,
    payload: dict,
    headers: dict | None = None,
    timeout: int = 45,
    max_attempts: int = 2,
    backoff_seconds: float = 0.8,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            response = requests.post(endpoint, json=payload, headers=headers or {}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        except Exception as error:
            logging.exception(error)
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            time.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return ""


def _groq_model_candidates() -> list[str]:
    primary = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    fallback = (os.getenv("GROQ_FALLBACK_MODEL") or "llama-3.1-8b-instant").strip()
    models: list[str] = []
    for model in [primary, fallback]:
        if model and model not in models:
            models.append(model)
    return models


def llm_json(messages: list[dict], temperature: float = 0.1, timeout: int = 45):
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = _call_openai_compatible_json(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    return parsed
            except Exception as e:
                logging.exception(e)
                stage = "Groq JSON call" if idx == 0 else "Groq JSON fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        parsed = _call_openai_compatible_json("https://text.pollinations.ai/openai", payload, timeout=timeout)
        if parsed is not None:
            return parsed
    except Exception as e:
        logging.error(f"[LLM] Pollinations JSON call failed (prompt_len={len(messages)}): {e}")

    try:
        from g4f.client import Client

        client = Client()
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            timeout=timeout,
        )
        content = res.choices[0].message.content.strip()
        parsed = _extract_json_payload(content)
        if parsed is not None:
            return parsed
    except Exception as e:
        logging.error(f"[LLM] g4f JSON fallback failed (prompt_len={len(messages)}): {e}")

    return {}


def llm_json_fast(messages: list[dict], temperature: float = 0.0, timeout: int = 12):
    """Fast-path JSON call for throughput-sensitive cleaning tasks."""
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = _call_openai_compatible_json(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    return parsed
            except Exception as e:
                logging.exception(e)
                stage = "Groq fast JSON call" if idx == 0 else "Groq fast JSON fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        parsed = _call_openai_compatible_json(
            "https://text.pollinations.ai/openai",
            payload,
            timeout=timeout,
        )
        if parsed is not None:
            return parsed
    except Exception as e:
        logging.exception(e)
        print(f"[LLM] Pollinations fast JSON call failed: {e}")

    return {}


def llm_text(messages: list[dict], temperature: float = 0.4, timeout: int = 45) -> str:
    groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                text = _call_openai_compatible_text(
                    "https://api.groq.com/openai/v1/chat/completions",
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if text:
                    return text
            except Exception as e:
                logging.exception(e)
                stage = "Groq text call" if idx == 0 else "Groq text fallback model call"
                print(f"[LLM] {stage} failed ({model}): {e}")

    try:
        payload = {
            "model": "openai",
            "messages": messages,
            "temperature": temperature,
        }
        text = _call_openai_compatible_text("https://text.pollinations.ai/openai", payload, timeout=timeout)
        if text:
            return text
    except Exception as e:
        logging.exception(e)
        print(f"[LLM] Pollinations text call failed: {e}")

    try:
        from g4f.client import Client

        client = Client()
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            timeout=timeout,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception as e:
        logging.exception(e)
        print(f"[LLM] g4f text fallback failed: {e}")
        return ""
