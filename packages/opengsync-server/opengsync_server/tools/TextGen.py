from google import genai

from .. import logger


class TextGen:
    def __init__(self):
        self._client = genai.Client()

    def generate(self, prompt: str, model: str = "gemini-2.5-flash", max_output_tokens: int = 256) -> str | None:
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    thinking_config=genai.types.ThinkingConfig(thinking_budget=0),
                    max_output_tokens=max_output_tokens
                ),
            )
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            return None
        
        return response.text