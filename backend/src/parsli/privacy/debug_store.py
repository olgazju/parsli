import json
from pathlib import Path


class DebugStore:
    """Writes debug artifacts to .parsli/debug/ when debug mode is enabled.

    All methods are silent no-ops when the store is disabled, so call-sites
    need no conditional logic around them.
    """

    def __init__(self, app_dir: Path, enabled: bool) -> None:
        self._enabled = enabled
        self._base = app_dir / "debug"

    def _ensure(self, subdir: str) -> Path:
        path = self._base / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def store_raw_email(self, email_id: str, raw_json: dict) -> None:
        if not self._enabled:
            return
        path = self._ensure("emails") / f"{email_id}.json"
        path.write_text(json.dumps(raw_json, ensure_ascii=False, indent=2))

    def store_cleaned_text(self, email_id: str, cleaned: str) -> None:
        if not self._enabled:
            return
        path = self._ensure("emails") / f"{email_id}.txt"
        path.write_text(cleaned, encoding="utf-8")

    def store_model_output(self, email_id: str, provider: str, output: dict) -> None:
        if not self._enabled:
            return
        path = self._ensure("model_outputs") / f"{email_id}.{provider}.json"
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
