"""Agent runtime entrypoint.

Loaded by every agent container. Reads the agent's manifest, imports
the user-supplied entrypoint, calls it, and prints a single
`__RESULT__ {json}` line that the worker parses to populate the run
row.

Required env vars (injected by the execution backend):
  RUN_ID, RUN_TOKEN, TOOL_GATEWAY_URL, RUN_INPUTS
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

RESULT_MARKER = "__RESULT__"
AGENT_DIR = Path("/agent")


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(f"{RESULT_MARKER} {json.dumps(payload, default=str)}\n")
    sys.stdout.flush()


def _load_manifest() -> dict[str, Any]:
    manifest_path = AGENT_DIR / "agent.yaml"
    if not manifest_path.exists():
        raise RuntimeError(f"agent.yaml not found at {manifest_path}")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "PyYAML is required to parse agent.yaml; install it in the agent image"
        ) from e
    return yaml.safe_load(manifest_path.read_text()) or {}


def _resolve_entrypoint(spec: str):
    if ":" not in spec:
        raise RuntimeError(f"entrypoint must be 'module:function', got {spec!r}")
    module_name, func_name = spec.split(":", 1)
    sys.path.insert(0, str(AGENT_DIR))
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        raise RuntimeError(f"entrypoint {spec!r} resolved but is not callable")
    return func


def main() -> int:
    for required in ("RUN_ID", "RUN_TOKEN", "TOOL_GATEWAY_URL"):
        if not os.environ.get(required):
            print(f"[agent-runtime] missing required env var {required}", file=sys.stderr)
            _emit({"__error__": f"missing env var {required}"})
            return 2

    try:
        manifest = _load_manifest()
        entrypoint_spec = manifest.get("entrypoint")
        if not entrypoint_spec:
            raise RuntimeError("agent.yaml is missing 'entrypoint'")
        run_func = _resolve_entrypoint(entrypoint_spec)
    except Exception as e:
        traceback.print_exc()
        _emit({"__error__": f"manifest/import failed: {e}"})
        return 2

    try:
        result = run_func()
    except Exception as e:
        traceback.print_exc()
        _emit({"__error__": f"agent raised: {type(e).__name__}: {e}"})
        return 1

    if result is None:
        result = {}
    if not isinstance(result, dict):
        result = {"value": result}
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
