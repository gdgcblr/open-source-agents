from google import genai
from google.genai import types
from knowflow.config import settings

class GeminiError(RuntimeError):
    """Raised when the Gemini API cannot produce a response."""


def chat(system: str, user: str) -> str:
    if not settings.gemini_api_key:
        raise GeminiError(
            "GEMINI_API_KEY is not configured. Create an API key in Google AI Studio and add it to your .env file."
        )
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.chat_model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.1,
            ),
        )
        content = (response.text or "").strip()
        if not content:
            raise GeminiError("Gemini returned an empty response. Try again or check the model and API quota.")
        return content
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(
            "Gemini API request failed. Check your internet connection, API key, model name, and API quota. "
            f"Details: {exc}"
        ) from exc
