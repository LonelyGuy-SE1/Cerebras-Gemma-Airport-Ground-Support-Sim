from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env", Path.cwd() / ".env"):
        if path.exists():
            values.update({key: str(value) for key, value in dotenv_values(path).items() if value is not None})
    values.update(os.environ)
    return values


def _first(values: dict[str, str], *names: str, default: str | None = None) -> str | None:
    for name in names:
        value = values.get(name)
        if value:
            return value
    return default


def _int_value(values: dict[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class ProviderSettings(BaseModel):
    name: str
    api_key: str | None
    base_url: str
    model: str
    simulated_delay_ms: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


class Settings(BaseModel):
    cerebras: ProviderSettings
    baseline: ProviderSettings
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    values = _load_env()
    cerebras = ProviderSettings(
        name="cerebras",
        api_key=_first(values, "CEREBRAS_API_KEY", "cerebras_key"),
        base_url=_first(values, "CEREBRAS_BASE_URL", default="https://api.cerebras.ai/v1")
        or "https://api.cerebras.ai/v1",
        model=_first(values, "CEREBRAS_MODEL", "model_name", default="gemma-4-31b") or "gemma-4-31b",
        simulated_delay_ms=_int_value(values, "CEREBRAS_SIMULATED_DELAY_MS", 220),
    )
    baseline = ProviderSettings(
        name="baseline",
        api_key=_first(values, "BASELINE_API_KEY", "OPENROUTER_API_KEY", "openrouter_key"),
        base_url=_first(values, "BASELINE_BASE_URL", default="https://openrouter.ai/api/v1")
        or "https://openrouter.ai/api/v1",
        model=_first(values, "BASELINE_MODEL", default="google/gemma-4-31b-it")
        or "google/gemma-4-31b-it",
        simulated_delay_ms=_int_value(values, "BASELINE_SIMULATED_DELAY_MS", 2600),
    )
    cors_raw = _first(
        values,
        "CORS_ORIGINS",
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5175,http://127.0.0.1:5175"
        ),
    ) or ""
    return Settings(
        cerebras=cerebras,
        baseline=baseline,
        cors_origins=[origin.strip() for origin in cors_raw.split(",") if origin.strip()],
    )
