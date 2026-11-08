#!/usr/bin/env bash
# Regenerate only the canonical generated-app Maven dependency/license evidence.
#
# Usage:
#   scripts/generate-generated-app-dependency-evidence.sh \
#     [SNAPSHOT_DATE] [MAVEN_LICENSE_PLUGIN_VERSION]
set -euo pipefail

SNAPSHOT_DATE="${1:-$(date +%F)}"
MAVEN_LICENSE_PLUGIN_VERSION="${2:-2.5.0}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/handover-evidence"
MANIFEST="$ROOT/examples/input-projects/generated-app-ci-smoke/app-definition.yaml"
PROJECT_PY="$ROOT/.venv/bin/python"
BASE_PY="$PROJECT_PY"
if [[ ! -x "$BASE_PY" ]]; then
  BASE_PY="$(command -v python3)"
fi

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/edgeforge-generated-app-evidence.XXXXXX")"
GEN_APP="$TMP_ROOT/generated-app"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

"$BASE_PY" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("generated-app evidence generation requires Python >= 3.11")
PY

mkdir -p "$OUT"

cd "$ROOT"
"$BASE_PY" -m appbuilder.cli generate \
  --manifest "$MANIFEST" \
  --output "$GEN_APP" \
  --validate-schema \
  --generation-run-id generated-app-dependency-evidence

mvn -q -f "$GEN_APP/pom.xml" dependency:tree \
  -DoutputFile="$OUT/generated-app-maven-dependency-tree.txt"

mvn -q -f "$GEN_APP/pom.xml" \
  "org.codehaus.mojo:license-maven-plugin:${MAVEN_LICENSE_PLUGIN_VERSION}:add-third-party" \
  -Dlicense.outputDirectory="$GEN_APP/target/generated-sources/license" \
  -Dlicense.thirdPartyFilename=THIRD-PARTY.txt

cp "$GEN_APP/target/generated-sources/license/THIRD-PARTY.txt" \
  "$OUT/generated-app-maven-third-party-licenses.txt"

SNAPSHOT_DATE="$SNAPSHOT_DATE" \
MAVEN_LICENSE_PLUGIN_VERSION="$MAVEN_LICENSE_PLUGIN_VERSION" \
  "$BASE_PY" - \
  "$OUT/generated-app-maven-third-party-licenses.txt" \
  "$OUT/generated-app-dependencies.md" <<'PY'
from __future__ import annotations

import os
import re
import sys

third_party, out_md = sys.argv[1], sys.argv[2]
text = open(third_party, encoding="utf-8", errors="replace").read()
unknown = [line.strip() for line in text.splitlines() if "unknown" in line.lower()]
notable_pattern = re.compile(r"GPL|LGPL|AGPL|MPL|EPL", re.I)
notable = [line.strip() for line in text.splitlines() if notable_pattern.search(line)]
if unknown or notable:
    fragments = []
    if unknown:
        fragments.append(f"{len(unknown)} UNKNOWN line(s)")
    if notable:
        fragments.append(f"{len(notable)} notable/copyleft-style license line(s)")
    status = (
        "**Generated-app Maven license report includes "
        + " and ".join(fragments)
        + ".** Disposition: listed in the raw report for adopter/security review; "
        "no automatic dependency change is made by this evidence refresh."
    )
else:
    status = (
        "**Generated-app Maven license report contains no UNKNOWN or "
        "notable/copyleft-style license lines.**"
    )

md = f"""# Generated-App Dependency Evidence — Canonical CI Smoke App

> **Import-gate G4 evidence.** Generated-app supply-chain snapshot for the
> canonical domain-neutral standalone app regenerated from
> `examples/input-projects/generated-app-ci-smoke/app-definition.yaml`.
>
> **Generated:** {os.environ['SNAPSHOT_DATE']}. Re-runnable via
> `scripts/generate-generated-app-dependency-evidence.sh`.

## Artifacts

| Artifact | Description |
|---|---|
| [`generated-app-maven-dependency-tree.txt`](generated-app-maven-dependency-tree.txt) | Maven dependency tree from the regenerated canonical CI smoke app. |
| [`generated-app-maven-third-party-licenses.txt`](generated-app-maven-third-party-licenses.txt) | Third-party license report from `org.codehaus.mojo:license-maven-plugin:{os.environ['MAVEN_LICENSE_PLUGIN_VERSION']}:add-third-party`. |

## Honest status

{status}

Generated apps are standalone Maven projects. This evidence is representative,
not a universal statement about every future generated app manifest.
"""
open(out_md, "w", encoding="utf-8").write(md)
print(
    "wrote generated-app Maven evidence; "
    f"unknown lines: {len(unknown)}; notable lines: {len(notable)}"
)
PY

echo "generated-app Maven evidence regenerated under $OUT/"
