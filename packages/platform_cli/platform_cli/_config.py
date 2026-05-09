"""CLI config: persists API URL + token + user info to ~/.platform/config.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def _config_path() -> Path:
    override = os.environ.get("PLATFORM_CLI_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".platform" / "config.json"


@dataclass
class CliConfig:
    api_url: str
    token: str
    email: str
    role: str
    tenant_id: str

    @classmethod
    def load(cls) -> "CliConfig":
        path = _config_path()
        if not path.exists():
            raise RuntimeError(
                "no CLI session — run `platform-cli login` first"
            )
        data = json.loads(path.read_text())
        return cls(**data)

    def save(self) -> None:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        # On POSIX, restrict to owner-readable so the token isn't world-visible.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def clear_config() -> None:
    path = _config_path()
    if path.exists():
        path.unlink()
