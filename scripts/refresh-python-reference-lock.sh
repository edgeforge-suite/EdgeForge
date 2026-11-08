#!/usr/bin/env bash
# Resolve declared Engine dependencies in the pinned Linux reference image.
# This intentionally changes the selected lock; review its diff and rerun proof.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="python:3.11.15-bookworm@sha256:a8f8fbe1a0edc9e4dddafa64ba73f7e04be7be5ebc23f332362e779e0a2e4e52"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

docker run --rm --platform linux/amd64 \
  --mount "type=bind,src=$ROOT/requirements.txt,dst=/requirements.txt,readonly" \
  --mount "type=bind,src=$TMP,dst=/output" \
  "$IMAGE" bash -c '
    set -euo pipefail
    python -m venv /tmp/engine
    /tmp/engine/bin/python -m pip install --quiet --disable-pip-version-check \
      -r /requirements.txt
    /tmp/engine/bin/python -m pip check
    /tmp/engine/bin/python -m pip freeze | LC_ALL=C sort > /output/freeze.txt
  '

{
  echo '# Engine reference dependency closure: CPython 3.11.15, Debian 12 x86_64.'
  echo '# Reference install only: python -m pip install -c requirements-lock.txt -r requirements.txt'
  echo '# This excludes installer bootstrap tools (pip, setuptools, wheel) and the local EdgeForge package.'
  echo '# Refresh only with a reviewed Python evidence update; platform-conditional packages may differ elsewhere.'
  cat "$TMP/freeze.txt"
} > "$ROOT/requirements-lock.txt"
