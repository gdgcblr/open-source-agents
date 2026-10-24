"""Ollama adapter restricted to a local loopback service."""

import re

import requests


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}\Z")


class OllamaUnavailable(RuntimeError):
    """Raised when local Ollama is unavailable or returns an invalid response."""


def explain_with_ollama(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_OLLAMA_MODEL,
) -> str:
    model_name = model.strip() if isinstance(model, str) else ""
    if not _MODEL_PATTERN.fullmatch(model_name) or "://" in model_name:
        raise OllamaUnavailable("Enter a valid Ollama model name.")

    session = None
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            OLLAMA_CHAT_URL,
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 250},
            },
            timeout=(3.0, 180.0),
            allow_redirects=False,
        )
        if response.status_code != 200:
            if response.status_code == 404:
                raise OllamaUnavailable(
                    "Ollama could not find the selected model. Pull it with "
                    "`ollama pull <model-name>` and try again."
                )
            if response.status_code == 429:
                raise OllamaUnavailable(
                    "Local Ollama is busy loading the model. Wait a moment and try again."
                )
            raise OllamaUnavailable("Local Ollama did not return a successful response.")
        payload = response.json()
        answer = payload["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise OllamaUnavailable("Ollama returned an empty response.")
        return answer.strip()
    except OllamaUnavailable:
        raise
    except requests.Timeout as exc:
        raise OllamaUnavailable(
            "Local Ollama took too long to respond. Try again, or select a smaller "
            "model if your computer has limited memory."
        ) from exc
    except requests.ConnectionError as exc:
        raise OllamaUnavailable(
            "Could not connect to Ollama at 127.0.0.1:11434. Install Ollama, start "
            "the Ollama app (or run `ollama serve`), and try again."
        ) from exc
    except requests.RequestException as exc:
        raise OllamaUnavailable(
            "The request to local Ollama failed. Check that it is running and try again."
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise OllamaUnavailable("Ollama returned an unreadable response.") from exc
    except Exception as exc:
        raise OllamaUnavailable(
            "Local Ollama encountered an unexpected error. Try again."
        ) from exc
    finally:
        if session is not None:
            session.close()
