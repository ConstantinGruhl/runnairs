from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def inspect_package(path: str | Path, entrypoint: str | None = None) -> dict[str, Any]:
    root = Path(path).resolve()
    resolved_entrypoint = entrypoint or _entrypoint_from_manifest(root)
    module_name, function_name = resolved_entrypoint.split(":", 1)

    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    sys.modules.pop(module_name, None)
    try:
        module = importlib.import_module(module_name)
    finally:
        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)

    if not hasattr(module, function_name):
        raise ValueError(f"entrypoint {resolved_entrypoint!r} is missing")

    meta = getattr(module, "AUTOMATION_META", {})
    if meta and not isinstance(meta, dict):
        raise ValueError("AUTOMATION_META must be a mapping when provided")

    module_specs = meta.get("modules", []) if isinstance(meta, dict) else []
    modules = [module_spec["id"] for module_spec in module_specs if isinstance(module_spec, dict) and module_spec.get("id")]
    if not modules:
        modules = ["default"]

    return {
        "runtime_api": meta.get("runtime_api", "v1") if isinstance(meta, dict) else "v1",
        "modules": modules,
        "triggers": list(meta.get("triggers", ["manual"])) if isinstance(meta, dict) else ["manual"],
        "channels": list(meta.get("channels", [])) if isinstance(meta, dict) else [],
        "entrypoint": resolved_entrypoint,
    }


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: python -m platform_sdk.inspect <path> [entrypoint]")

    path = Path(args[0])
    entrypoint = args[1] if len(args) > 1 else None
    print(json.dumps(inspect_package(path, entrypoint=entrypoint), indent=2, sort_keys=True))


def _entrypoint_from_manifest(root: Path) -> str:
    for filename in ("automation.yaml", "agent.yaml"):
        manifest_path = root / filename
        if not manifest_path.exists():
            continue
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict) or not raw.get("entrypoint"):
            raise ValueError(f"{filename} must declare entrypoint")
        return str(raw["entrypoint"])
    raise ValueError("package is missing automation.yaml or agent.yaml")


if __name__ == "__main__":
    main()
