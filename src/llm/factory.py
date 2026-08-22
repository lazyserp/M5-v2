import os
from typing import Optional
from src.llm.base import BaseLLMProvider
from src.llm.gemini_provider import GeminiProvider
from src.llm.openai_compatible_provider import OpenAICompatibleProvider

def get_llm_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model_id: Optional[str] = None,
    base_url: Optional[str] = None
) -> BaseLLMProvider:
    """
    Factory creating the configured LLM Provider.
    Supported: 'gemini' (default), 'vllm', 'ollama', 'azure', 'local'.
    """
    target_provider = (provider_name or os.getenv("LLM_PROVIDER", "gemini")).lower().strip()

    if target_provider in ["vllm", "ollama", "azure", "local", "openai"]:
        return OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            model_id=model_id
        )
    else:
        return GeminiProvider(
            api_key=api_key,
            model_id=model_id
        )
