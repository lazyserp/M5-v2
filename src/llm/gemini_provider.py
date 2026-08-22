import os
from typing import Optional
from google import genai
from src.llm.base import BaseLLMProvider
from src.config import GEMINI_API_KEY

class GeminiProvider(BaseLLMProvider):
    """Google AI Studio / Vertex AI Gemini Model Provider."""
    def __init__(self, api_key: Optional[str] = None, model_id: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.model_id = model_id or os.getenv("MODEL_ID", "gemini-3.7-flash")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def generate_content(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        if not self.client:
            raise ValueError("[ERROR] GEMINI_API_KEY is not configured.")
        
        full_content = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=full_content
        )
        return (response.text or "").strip()
