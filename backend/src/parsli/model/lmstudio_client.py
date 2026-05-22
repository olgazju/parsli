"""LM Studio local model client.

LM Studio exposes an OpenAI-compatible REST API. We use the chat/completions
endpoint with JSON mode to get structured responses.
"""

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..config import ModelConfig
from .base import ModelExtractionResult

T = TypeVar("T", bound=BaseModel)

_DEFAULT_ENDPOINT = "http://localhost:1234"


class LMStudioClient:
    """Extracts structured data from email text using a locally-running LM Studio model.

    Args:
        config: ModelConfig with endpoint_url and model_name.
    """

    def __init__(self, config: ModelConfig) -> None:
        base = (config.endpoint_url or _DEFAULT_ENDPOINT).rstrip("/")
        self._url = f"{base}/v1/chat/completions"
        self._model = config.model_name
        self._timeout = config.timeout_seconds

    def extract(self, prompt: str, *, response_model: type[T]) -> T:
        """Send prompt to LM Studio and parse the JSON response into response_model."""
        schema = response_model.model_json_schema()
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema, "strict": True},
            },
            "temperature": 0.1,
            "stream": False,
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
        return response_model.model_validate(data)
