"""llama-cpp-python server client.

The llama-cpp server exposes a /completion endpoint that accepts a grammar
parameter for constrained JSON generation.
"""

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..config import ModelConfig

T = TypeVar("T", bound=BaseModel)

_DEFAULT_ENDPOINT = "http://localhost:8080"


class LlamaCppClient:
    """Extracts structured data using a locally-running llama-cpp-python server.

    Args:
        config: ModelConfig with endpoint_url.
    """

    def __init__(self, config: ModelConfig) -> None:
        base = (config.endpoint_url or _DEFAULT_ENDPOINT).rstrip("/")
        self._url = f"{base}/v1/chat/completions"
        self._model = config.model_name
        self._timeout = config.timeout_seconds

    def extract(self, prompt: str, *, response_model: type[T]) -> T:
        """Send prompt to llama-cpp server and parse the JSON response."""
        schema = response_model.model_json_schema()
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": schema},
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
