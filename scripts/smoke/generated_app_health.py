#!/usr/bin/env python3
"""Require healthy aggregate and component status, allowing Actuator metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def healthy_response(value: object) -> bool:
    if not isinstance(value, dict) or value.get("status") != "UP":
        return False
    components = value.get("components", {})
    return isinstance(components, dict) and all(
        healthy_response(component) for component in components.values()
    )


def main() -> int:
    try:
        value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, ValueError):
        return 1
    return 0 if healthy_response(value) else 1


if __name__ == "__main__":
    sys.exit(main())
