from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


@dataclass(frozen=True)
class PackageDescriptor:
    format: str
    manifest_path: str
    data: dict[str, Any]


def load_package_descriptor(root: Path) -> PackageDescriptor:
    for filename, fmt in (("automation.yaml", "automation"), ("agent.yaml", "legacy_agent")):
        path = root / filename
        if not path.exists():
            continue
        raw = _load_yaml_mapping(path)
        if fmt == "legacy_agent":
            normalized = normalize_legacy_agent_manifest(raw)
        else:
            normalized = normalize_automation_manifest(raw)
        validate_descriptor(normalized, source=filename)
        return PackageDescriptor(format=fmt, manifest_path=filename, data=normalized)
    raise ValueError("archive is missing automation.yaml or agent.yaml at the top level")


def normalize_stored_descriptor(
    manifest: dict[str, Any] | None,
    *,
    descriptor_format: str | None = None,
) -> dict[str, Any]:
    if not manifest:
        return {}

    raw = dict(manifest)
    if _is_legacy_descriptor(raw, descriptor_format=descriptor_format):
        return normalize_legacy_agent_manifest(raw)
    return normalize_automation_manifest(raw)


def validate_descriptor(descriptor: dict[str, Any], *, source: str) -> None:
    for field in ("name", "display_name", "entrypoint", "modules"):
        if not descriptor.get(field):
            raise ValueError(f"{source} missing required field: {field}")

    slug = descriptor["name"]
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise ValueError(
            f"{source} `name` must match ^[a-z][a-z0-9-]{{0,62}}$ (lowercase, hyphens)"
        )

    entrypoint = descriptor["entrypoint"]
    if ":" not in str(entrypoint):
        raise ValueError(f"{source} entrypoint must look like module:function")

    modules = descriptor["modules"]
    if not isinstance(modules, list):
        raise ValueError(f"{source} modules must be a list")
    for module in modules:
        if not isinstance(module, dict) or not module.get("id"):
            raise ValueError(f"{source} modules entries must be mappings with an id")

    _require_string_list(descriptor.get("tools") or [], field="tools", source=source)
    _require_string_list(
        descriptor.get("workspace_connections") or [],
        field="workspace_connections",
        source=source,
    )
    _require_string_list(
        descriptor.get("user_connections") or [],
        field="user_connections",
        source=source,
    )
    _require_string_list(
        descriptor.get("approvals_required_for") or [],
        field="approvals_required_for",
        source=source,
    )
    _require_string_list(
        descriptor.get("http_allowlist") or [],
        field="http_allowlist",
        source=source,
    )

    if "http.request" in (descriptor.get("tools") or []) and not descriptor.get("http_allowlist"):
        raise ValueError(
            f"{source} declares http.request but has no http_allowlist"
        )


def normalize_legacy_agent_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    permissions = manifest.get("permissions") or {}
    approvals = manifest.get("approvals") or {}
    http_allowlist = list(permissions.get("http_allowlist") or [])
    workspace_connections = [
        secret["name"]
        for secret in permissions.get("secrets") or []
        if isinstance(secret, dict) and secret.get("scope") == "workspace" and secret.get("name")
    ]
    user_connections = [
        secret["name"]
        for secret in permissions.get("secrets") or []
        if isinstance(secret, dict) and secret.get("scope") == "user" and secret.get("name")
    ]
    approvals_required_for = list(approvals.get("required_for") or [])
    tools = list(permissions.get("tools") or [])

    normalized = dict(manifest)
    normalized.update(
        {
            "display_name": manifest.get("display_name") or manifest["name"],
            "description": manifest.get("description"),
            "inputs": manifest.get("inputs") or {},
            "tools": tools,
            "workspace_connections": workspace_connections,
            "user_connections": user_connections,
            "approvals_required_for": approvals_required_for,
            "http_allowlist": http_allowlist,
            "modules": [
                {
                    "id": "default",
                    "title": manifest.get("display_name") or manifest["name"],
                    "required": True,
                    "enabled_by_default": True,
                }
            ],
            "limits": manifest.get("limits") or {},
            "compatibility": {"runtime_api": "v1"},
            "permissions": {
                "tools": tools,
                "secrets": list(permissions.get("secrets") or []),
                "http_allowlist": http_allowlist,
            },
            "approvals": {"required_for": approvals_required_for},
        }
    )
    return normalized


def normalize_automation_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    workspace_connections = list(manifest.get("workspace_connections") or [])
    user_connections = list(manifest.get("user_connections") or [])
    tools = list(manifest.get("tools") or [])
    approvals_required_for = list(manifest.get("approvals_required_for") or [])
    http_allowlist = list(manifest.get("http_allowlist") or [])
    compatibility = dict(manifest.get("compatibility") or {})
    compatibility.setdefault("runtime_api", "v2")

    normalized = dict(manifest)
    normalized.update(
        {
            "display_name": manifest.get("display_name") or manifest["name"],
            "description": manifest.get("description"),
            "inputs": manifest.get("inputs") or {},
            "workspace_connections": workspace_connections,
            "user_connections": user_connections,
            "tools": tools,
            "approvals_required_for": approvals_required_for,
            "http_allowlist": http_allowlist,
            "modules": list(manifest.get("modules") or []),
            "limits": manifest.get("limits") or {},
            "compatibility": compatibility,
            "permissions": {
                "tools": tools,
                "secrets": [
                    *[
                        {"name": name, "scope": "workspace"}
                        for name in workspace_connections
                    ],
                    *[
                        {"name": name, "scope": "user"}
                        for name in user_connections
                    ],
                ],
                "http_allowlist": http_allowlist,
            },
            "approvals": {"required_for": approvals_required_for},
        }
    )
    return normalized


def _is_legacy_descriptor(
    manifest: dict[str, Any],
    *,
    descriptor_format: str | None,
) -> bool:
    if descriptor_format == "legacy_agent":
        return True
    if descriptor_format == "automation":
        return False

    runtime_api = (manifest.get("compatibility") or {}).get("runtime_api")
    if runtime_api == "v1":
        return True
    if runtime_api == "v2":
        return False

    has_canonical_fields = any(
        key in manifest
        for key in (
            "modules",
            "tools",
            "workspace_connections",
            "user_connections",
            "approvals_required_for",
        )
    )
    return "permissions" in manifest and not has_canonical_fields


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name} parse error: {e}") from e
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} must be a mapping at the top level")
    return raw


def _require_string_list(values: list[Any], *, field: str, source: str) -> None:
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"{source} {field} must be a list of strings")
