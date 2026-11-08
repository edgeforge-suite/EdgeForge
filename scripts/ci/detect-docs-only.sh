#!/usr/bin/env bash

set -euo pipefail

ZERO_SHA="0000000000000000000000000000000000000000"
EVENT_NAME="${EVENT_NAME:-${GITHUB_EVENT_NAME:-}}"
HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-}}"
BEFORE_SHA="${BEFORE_SHA:-}"
PR_BASE_SHA="${PR_BASE_SHA:-}"
PR_HEAD_SHA="${PR_HEAD_SHA:-}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
REF_NAME="${REF_NAME:-${GITHUB_REF_NAME:-}}"

is_commit() {
  local revision="$1"
  [[ -n "$revision" ]] && git cat-file -e "${revision}^{commit}" 2>/dev/null
}

default_branch_ref() {
  local remote_ref="refs/remotes/origin/${DEFAULT_BRANCH}"

  if ! is_commit "$remote_ref"; then
    git fetch --no-tags origin \
      "+refs/heads/${DEFAULT_BRANCH}:${remote_ref}" >/dev/null 2>&1 || true
  fi

  if is_commit "$remote_ref"; then
    printf '%s\n' "$remote_ref"
  fi
}

merge_base_for_head() {
  local head="$1"
  local default_ref

  default_ref="$(default_branch_ref)"
  if [[ -n "$default_ref" ]] && is_commit "$head"; then
    git merge-base "$default_ref" "$head" 2>/dev/null || true
  fi
}

comparison_base=""
comparison_head=""
comparison_kind="unknown"

if [[ "$EVENT_NAME" == "pull_request" ]]; then
  if is_commit "$PR_BASE_SHA" && is_commit "$PR_HEAD_SHA"; then
    comparison_base="$PR_BASE_SHA"
    comparison_head="$PR_HEAD_SHA"
    comparison_kind="pull-request"
  elif is_commit "$PR_HEAD_SHA"; then
    comparison_base="$(merge_base_for_head "$PR_HEAD_SHA")"
    if is_commit "$comparison_base"; then
      comparison_head="$PR_HEAD_SHA"
      comparison_kind="merge-base"
    fi
  fi
elif [[ "$EVENT_NAME" == "push" ]] && is_commit "$HEAD_SHA"; then
  if [[ -n "$BEFORE_SHA" && "$BEFORE_SHA" != "$ZERO_SHA" ]] \
    && is_commit "$BEFORE_SHA" \
    && git merge-base --is-ancestor "$BEFORE_SHA" "$HEAD_SHA" 2>/dev/null; then
    comparison_base="$BEFORE_SHA"
    comparison_head="$HEAD_SHA"
    comparison_kind="push"
  elif [[ "$REF_NAME" != "$DEFAULT_BRANCH" ]]; then
    comparison_base="$(merge_base_for_head "$HEAD_SHA")"
    if is_commit "$comparison_base"; then
      comparison_head="$HEAD_SHA"
      comparison_kind="merge-base"
    fi
  fi
fi

docs_only="false"
if is_commit "$comparison_base" && is_commit "$comparison_head"; then
  if files="$(git diff --name-only "$comparison_base" "$comparison_head" 2>/dev/null)"; then
    non_doc_files="$(printf '%s\n' "$files" | grep -Ev '^(docs/|.*\.md$)' || true)"
    python_evidence_files="$(printf '%s\n' "$files" | grep -E '^docs/handover-evidence/python-current/' || true)"
    if [[ -z "$non_doc_files" && -z "$python_evidence_files" ]]; then
      docs_only="true"
    fi
  else
    comparison_kind="unknown"
  fi
fi

if [[ "$comparison_kind" == "unknown" ]]; then
  docs_only="false"
  echo "No trustworthy comparison base was available; running the full Python test suite."
else
  echo "Docs-only detection used ${comparison_kind}: ${comparison_base}..${comparison_head}"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'docs_only=%s\n' "$docs_only" >> "$GITHUB_OUTPUT"
  printf 'comparison_kind=%s\n' "$comparison_kind" >> "$GITHUB_OUTPUT"
else
  printf 'docs_only=%s\n' "$docs_only"
  printf 'comparison_kind=%s\n' "$comparison_kind"
fi
