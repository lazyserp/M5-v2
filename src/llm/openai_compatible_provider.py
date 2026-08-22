import os
import json
import urllib.request
import urllib.error
from typing import Optional
from src.llm.base import BaseLLMProvider

class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Air-Gapped & Local LLM Provider for self-hosted vLLM, Ollama, or Azure OpenAI.
    Communicates via standard OpenAI v1/chat/completions REST endpoint.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None
    ):
        self.base_url = (base_url or os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LOCAL_LLM_API_KEY", "EMPTY")
        self.model_id = model_id or os.getenv("LOCAL_MODEL_ID", "qwen2.5-coder:7b")

    def generate_content(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        url = f"{self.base_url}/chat/completions"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.1
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"].strip()
        except urllib.error.URLError as e:
            raise ConnectionError(f"[ERROR] Failed to connect to Local LLM at {url}: {str(e)}")
