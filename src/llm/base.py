from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseLLMProvider(ABC):
    """
    Abstract LLM Provider interface enabling zero-vendor-lockin deployment.
    Supports Cloud APIs (Google Gemini, Azure OpenAI) and Air-Gapped Local Models (vLLM, Ollama).
    """
    @abstractmethod
    def generate_content(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generates a text completion given a prompt context."""
        pass
