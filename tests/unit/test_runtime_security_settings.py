from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]


def _load_settings_class(monkeypatch: pytest.MonkeyPatch, *, relative_path: str, module_name: str):
    # Keep module-level Settings() construction in development mode while importing.
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "devsecret")

    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module at {relative_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Settings


@pytest.mark.parametrize(
    ("relative_path", "module_name"),
    [
        ("services/control-plane/app/core/config.py", "control_plane_runtime_config"),
        ("services/tool-gateway/app/config.py", "tool_gateway_runtime_config"),
    ],
)
def test_production_requires_strong_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    module_name: str,
) -> None:
    Settings = _load_settings_class(
        monkeypatch,
        relative_path=relative_path,
        module_name=module_name,
    )

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(ValidationError, match="JWT_SECRET must be set to a strong"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("relative_path", "module_name"),
    [
        ("services/control-plane/app/core/config.py", "control_plane_runtime_config_ok"),
        ("services/tool-gateway/app/config.py", "tool_gateway_runtime_config_ok"),
    ],
)
def test_production_accepts_strong_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    module_name: str,
) -> None:
    Settings = _load_settings_class(
        monkeypatch,
        relative_path=relative_path,
        module_name=module_name,
    )

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    settings = Settings(_env_file=None)

    assert settings.app_env == "production"
