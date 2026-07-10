"""Validated configuration, precedence, and platform-aware generated-state paths."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_config_path, user_data_path, user_log_path, user_runtime_path
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from global_memory.errors import ErrorCode, GlobalMemoryError

APP_NAME = "global-memory"
ENV_PREFIX = "GLOBAL_MEMORY_"


class MCPSettings(BaseModel):
    """Local MCP transport configuration."""

    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    transport: Literal["streamable-http"] = "streamable-http"
    require_local_token: bool = True
    max_request_bytes: int = Field(default=1_048_576, ge=1024, le=16_777_216)


class IndexSettings(BaseModel):
    """Filesystem and chunking behavior."""

    watch: bool = True
    debounce_ms: int = Field(default=500, ge=50, le=60_000)
    excluded_globs: list[str] = Field(default_factory=lambda: [".obsidian/**", ".trash/**"])
    chunk_target_tokens: int = Field(default=550, ge=100, le=4000)
    chunk_overlap_tokens: int = Field(default=50, ge=0, le=500)


class SearchSettings(BaseModel):
    """Retrieval defaults and bounded candidate counts."""

    default_mode: Literal["hybrid", "keyword", "semantic", "metadata"] = "hybrid"
    keyword_candidates: int = Field(default=50, ge=1, le=1000)
    semantic_candidates: int = Field(default=50, ge=1, le=1000)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    max_results: int = Field(default=100, ge=1, le=100)


class EmbeddingSettings(BaseModel):
    """Optional local embedding provider configuration."""

    enabled: bool = True
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "nomic-embed-text"
    batch_size: int = Field(default=32, ge=1, le=512)


class IntegrationSettings(BaseModel):
    """Client integration installation defaults."""

    prefer_symlinks: bool = True
    manage_global_instructions: bool = False


class GlobalMemorySettings(BaseSettings):
    """Complete service configuration after precedence resolution."""

    model_config = SettingsConfigDict(extra="forbid")

    vault_path: Path
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)


@dataclass(frozen=True, slots=True)
class PlatformPaths:
    """Generated-state locations kept outside the canonical Vault."""

    config_dir: Path
    data_dir: Path
    log_dir: Path
    runtime_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def auth_token(self) -> Path:
        return self.config_dir / "auth-token"

    @property
    def database(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vector"


def get_platform_paths() -> PlatformPaths:
    """Resolve OS-native paths through platformdirs in one place."""
    runtime = user_runtime_path(APP_NAME, ensure_exists=False)
    data = user_data_path(APP_NAME, ensure_exists=False)
    return PlatformPaths(
        config_dir=user_config_path(APP_NAME, ensure_exists=False),
        data_dir=data,
        log_dir=user_log_path(APP_NAME, ensure_exists=False),
        runtime_dir=runtime if runtime is not None else data / "run",
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _environment_values() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name, value in os.environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        keys = name[len(ENV_PREFIX) :].lower().split("__")
        cursor = values
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = value
    return values


def load_settings(config_file: Path | None = None, cli_overrides: dict[str, Any] | None = None) -> GlobalMemorySettings:
    """Load file < environment < CLI precedence and translate validation errors."""
    source: dict[str, Any] = {}
    if config_file is not None and config_file.exists():
        try:
            with config_file.open("rb") as stream:
                source = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise GlobalMemoryError(
                ErrorCode.CONFIG_INVALID,
                "The configuration file could not be read.",
                details={"path": str(config_file), "reason": str(exc)},
                remediation="Fix the TOML syntax or regenerate the configuration.",
            ) from exc
    source = _deep_merge(source, _environment_values())
    source = _deep_merge(source, cli_overrides or {})
    errors: list[dict[str, str]] = []
    vault_value = source.get("vault_path")
    if vault_value is not None and not Path(vault_value).expanduser().is_absolute():
        errors.append({"field": "vault_path", "message": "Path must be absolute."})
    try:
        settings = GlobalMemorySettings.model_validate(source)
    except ValidationError as exc:
        errors.extend(
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]} for error in exc.errors()
        )
        settings = None
    if errors or settings is None:
        raise GlobalMemoryError(
            ErrorCode.CONFIG_INVALID,
            "Configuration validation failed.",
            details={"errors": errors},
            remediation="Correct every listed field and run `global-memory config validate` again.",
        )
    settings.vault_path = settings.vault_path.expanduser()
    return settings


def render_config(settings: GlobalMemorySettings) -> str:
    """Render deterministic TOML without serializing secrets."""
    excluded = ", ".join(f'"{item}"' for item in settings.index.excluded_globs)
    return (
        f'vault_path = "{settings.vault_path}"\n'
        f'log_level = "{settings.log_level}"\n\n'
        "[mcp]\n"
        f'host = "{settings.mcp.host}"\nport = {settings.mcp.port}\n'
        f'transport = "{settings.mcp.transport}"\n'
        f"require_local_token = {str(settings.mcp.require_local_token).lower()}\n"
        f"max_request_bytes = {settings.mcp.max_request_bytes}\n\n"
        "[index]\n"
        f"watch = {str(settings.index.watch).lower()}\ndebounce_ms = {settings.index.debounce_ms}\n"
        f"excluded_globs = [{excluded}]\nchunk_target_tokens = {settings.index.chunk_target_tokens}\n"
        f"chunk_overlap_tokens = {settings.index.chunk_overlap_tokens}\n\n"
        "[search]\n"
        f'default_mode = "{settings.search.default_mode}"\nkeyword_candidates = {settings.search.keyword_candidates}\n'
        f"semantic_candidates = {settings.search.semantic_candidates}\nrrf_k = {settings.search.rrf_k}\n"
        f"max_results = {settings.search.max_results}\n\n"
        "[embeddings]\n"
        f'enabled = {str(settings.embeddings.enabled).lower()}\nprovider = "{settings.embeddings.provider}"\n'
        f'base_url = "{settings.embeddings.base_url}"\nmodel = "{settings.embeddings.model}"\n'
        f"batch_size = {settings.embeddings.batch_size}\n\n"
        "[integrations]\n"
        f"prefer_symlinks = {str(settings.integrations.prefer_symlinks).lower()}\n"
        f"manage_global_instructions = {str(settings.integrations.manage_global_instructions).lower()}\n"
    )
