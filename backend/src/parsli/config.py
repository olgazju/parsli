from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LanguageConfig(BaseModel):
    """Which language packs are active for this instance.

    Defaults to English + Hebrew. The processing components build their
    patterns exclusively from the active language packs, so adding or
    removing a code here changes every regex, query term, and shipping
    signal without touching Python source.
    """

    enabled: list[str] = Field(default_factory=lambda: ["en", "he"])


class GmailConfig(BaseModel):
    lookback_days: int = 60
    query_category_filter: str = ""  # e.g. "(category:updates OR category:primary)"
    # Filtered at Gmail query level and also checked by RuleEngine at
    # classification time (belt-and-suspenders). Not language-specific.
    default_exclude_domains: list[str] = Field(default_factory=lambda: [
        "payplus.co.il",
        "paypal.com",
        "stripe.com",
        "cardcom.co.il",
        "tranzila.com",
        "isracard.co.il",
        "booking.com",
    ])


class ModelConfig(BaseModel):
    provider: Literal["lmstudio", "llamacpp"] = "lmstudio"
    endpoint_url: str | None = None
    model_name: str = "gemma-3-4b"
    timeout_seconds: int = 120
    # Text size sent to the model per mode. Required gets a full email body;
    # audit only needs a short preview since rules already classified the email.
    required_max_chars: int = 4000
    audit_max_chars: int = 1500


class PrivacyConfig(BaseModel):
    debug_store_email_artifacts: bool = False
    evidence_max_chars: int = 240


class ProcessingConfig(BaseModel):
    rules_version: str = "v1"
    prompt_version: str = "v2"
    merge_version: str = "v1"
    incremental_batch_size: int = 100

    def processing_version(self) -> str:
        return f"rules:{self.rules_version};prompt:{self.prompt_version}"


class DatabaseConfig(BaseModel):
    sqlite_path: Path = Path(".parsli/parsli.db")


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PARSLI_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_dir: Path = Path(".parsli")
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    gmail: GmailConfig = Field(default_factory=GmailConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @property
    def credentials_path(self) -> Path:
        return self.app_dir / "credentials.json"

    @property
    def tokens_dir(self) -> Path:
        return self.app_dir / "tokens"
