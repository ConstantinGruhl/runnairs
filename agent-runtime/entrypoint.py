"""Agent runtime entrypoint.

Loads agent.yaml, imports the agent's main module, calls the run function,
and posts the result back to the control plane. Real implementation lands
in Phase 4.
"""

import sys


def main() -> int:
    print("agent-runtime placeholder; replace in Phase 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
