"""Typed configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class RetryConfig(BaseModel):
    """Retry policy used for Graph and OpenAI calls."""

    attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.2


class PathsConfig(BaseModel):
    """Output and state paths."""

    output_root: str = "artifacts"
    exports_dir: str = "exports"
    review_dir: str = "manual_review"
    logs_dir: str = "logs"
    runs_dir: str = "runs"
    state_db: str = "state/pipeline_state.sqlite3"


class SourceConfig(BaseModel):
    """Message source configuration."""

    provider: str = "fixture"
    user_email: str = ""
    fixture_path: str = "tests/fixtures/mock_outlook_inbox.json"
    fixture_llm_path: str = "tests/fixtures/mock_llm_responses.json"
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""


class OpenAIConfig(BaseModel):
    """OpenAI settings used for live LLM extraction."""

    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 30.0


class AppConfig(BaseModel):
    """Top-level application configuration."""

    model_config = ConfigDict(extra="ignore")

    app_name: str = "Order Info Extractor Demo"
    catalog_path: str = "src/product_catalog.json"
    confidence_threshold: float = 0.82
    source: SourceConfig = Field(default_factory=SourceConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    _base_dir: Path = PrivateAttr(default_factory=Path.cwd)

    def resolve_path(self, value: str) -> Path:
        """Resolve a possibly-relative path against the config directory."""

        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return (self._base_dir / candidate).resolve()

    def output_path(self, *parts: str) -> Path:
        """Resolve a path under the configured output root."""

        root = self.resolve_path(self.paths.output_root)
        return root.joinpath(*parts)


def load_config(path: Optional[str] = None) -> AppConfig:
    """Load config from JSON and attach its base directory."""

    candidate_paths = []
    if path:
        candidate_paths.append(Path(path))
    else:
        candidate_paths.extend([Path("config.json"), Path("config.example.json")])

    for candidate in candidate_paths:
        if candidate.exists():
            config = AppConfig.model_validate(json.loads(candidate.read_text()))
            config._base_dir = candidate.resolve().parent
            return config

    config = AppConfig()
    config._base_dir = Path.cwd()
    return config

