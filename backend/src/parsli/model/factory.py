from ..config import ModelConfig
from .base import LocalModelClient
from .llamacpp_client import LlamaCppClient
from .lmstudio_client import LMStudioClient


class ModelClientFactory:
    """Creates the appropriate LocalModelClient for the configured provider."""

    @staticmethod
    def create(config: ModelConfig) -> LocalModelClient:
        if config.provider == "lmstudio":
            return LMStudioClient(config)
        if config.provider == "llamacpp":
            return LlamaCppClient(config)
        raise ValueError(f"Unknown model provider: {config.provider!r}")
