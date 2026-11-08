#!/usr/bin/env bash
# Rebuild only the Engine Python dependency evidence in the pinned Linux reference image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="python:3.11.15-bookworm@sha256:a8f8fbe1a0edc9e4dddafa64ba73f7e04be7be5ebc23f332362e779e0a2e4e52"
OUT="docs/handover-evidence/python-current"
ENGINE_SOURCE_SHA="$(git -C "$ROOT" rev-parse HEAD)"
mkdir -p "$ROOT/$OUT"

docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$ROOT,dst=/src,readonly" \
  --mount "type=bind,src=$ROOT/$OUT,dst=/evidence" \
  --env "ENGINE_SOURCE_SHA=$ENGINE_SOURCE_SHA" \
  --env "REFERENCE_IMAGE=$IMAGE" \
  "$IMAGE" bash -c '
    set -euo pipefail
    python -m venv /tmp/engine
    /tmp/engine/bin/python -m pip install --quiet --disable-pip-version-check \
      -c /src/requirements-lock.txt -r /src/requirements.txt
    /tmp/engine/bin/python -m pip check
    python -m venv /tmp/evidence-tools
    /tmp/evidence-tools/bin/python -m pip install --quiet --disable-pip-version-check \
      cyclonedx-bom==7.3.0 pip-licenses==5.5.5 pip-audit==2.9.0
    /tmp/engine/bin/python /src/scripts/generate_python_dependency_evidence.py \
      --requirements /src/requirements.txt \
      --lock /src/requirements-lock.txt \
      --python /tmp/engine/bin/python \
      --cyclonedx /tmp/evidence-tools/bin/cyclonedx-py \
      --licenses /tmp/evidence-tools/bin/pip-licenses \
      --scanner /tmp/evidence-tools/bin/pip-audit \
      --output /evidence \
      --engine-sha "$ENGINE_SOURCE_SHA" \
      --reference-image "$REFERENCE_IMAGE"
  '
