from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QueryVocabulary(BaseModel):
    """Developer-controlled keyword groups used to build Gmail candidate queries.

    Split into named groups so the query builder can emit targeted named queries
    rather than one large OR clause — making it easy to debug why a message
    was fetched and to tune signal-to-noise per group.
    """

    strong_shipping: list[str] = Field(default_factory=lambda: [
        "shipped",
        "delivered",
        '"tracking number"',
        '"out for delivery"',
        '"estimated delivery"',
        "dispatch",
        "customs",
        '"מספר מעקב"',
        '"ההזמנה נשלחה"',
        '"ההזמנה שלך נשלחה"',
        '"המשלוח נשלח"',
        '"מספר מעקב"',
        '"מוכן לאיסוף"',
        '"יצא לדרך"',
    ])
    package_words: list[str] = Field(default_factory=lambda: [
        '"your package"',
        '"your shipment"',
        '"your parcel"',
        "חבילה",
        "משלוח",
    ])
    order_lifecycle: list[str] = Field(default_factory=lambda: [
        '"order confirmation"',
        '"thanks for your order"',
        '"your order has shipped"',
        '"your order is on its way"',
        '"אישור ההזמנה"',
        '"הזמנתך התקבלה"',
    ])
    weak_phrases: list[str] = Field(default_factory=lambda: [
        '"on its way"',
        '"your order"',
    ])
    # Applied to every query
    exclude_terms: list[str] = Field(default_factory=lambda: [
        "פרסומת",
        '"סיכום חודש"',
        '"חשבונית מס"',
        '"חשבונית מס קבלה"',
        '"Tax Invoice"',
        '"פירוט חיובים"',
        '"חיובים תקופתיים"',
        "unsubscribe",
        "booking",
        "ticket",
        "tickets",
    ])
    # Extra exclusions applied only to the weak_phrases query to reduce noise
    weak_phrase_exclusions: list[str] = Field(default_factory=lambda: [
        '"your request"',
        '"request is on its way"',
    ])
    # Filtered at Gmail query level — never downloaded
    default_exclude_domains: list[str] = Field(default_factory=lambda: [
        "payplus.co.il",
        "paypal.com",
        "stripe.com",
        "cardcom.co.il",
        "tranzila.com",
        "isracard.co.il",
        "booking.com"
    ])


class GmailConfig(BaseModel):
    lookback_days: int = 60
    query_category_filter: str = ""  # e.g. "(category:updates OR category:primary)"
    vocabulary: QueryVocabulary = Field(default_factory=QueryVocabulary)


class ModelConfig(BaseModel):
    provider: Literal["lmstudio", "llamacpp"] = "lmstudio"
    endpoint_url: str | None = None
    model_name: str = "gemma-3-4b"
    timeout_seconds: int = 120
    max_input_chars: int = 1500


class PrivacyConfig(BaseModel):
    debug_store_email_artifacts: bool = False
    evidence_max_chars: int = 240


class ProcessingConfig(BaseModel):
    rules_version: str = "v1"
    prompt_version: str = "v1"
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
