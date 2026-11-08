#!/usr/bin/env bash
# Retained as a safe refusal for callers of the former mixed Python/Maven script.
set -euo pipefail

printf '%s\n' \
  'This legacy command is disabled: it could overwrite the selected Python lock and dated evidence.' \
  'Use make lock for a reviewed reference lock refresh, make sbom for current Python evidence,' \
  'or scripts/generate-generated-app-dependency-evidence.sh for Maven evidence.' >&2
exit 2
