#!/usr/bin/env bash
# Saringan quality-gate adapter for Rangkai.
#
# Contract with Rangkai:
# - invoked as an external CLI from quality_gate.command
# - prints one Saringan-compatible Validation Result JSON object to stdout
# - exits 0 when it produced a parseable result, even if that result is failed/error
# - reserves non-zero exits for wrapper crashes before it can emit JSON
#
# Usage:
#   saringan-quality-gate.sh <worktree_path> <issue_number> <prd_branch> <implementation_branch>
#
# Environment:
#   SARINGAN_BIN          Path/name of saringan executable. Default: saringan
#   SARINGAN_JUDGE_MODEL  LiteLLM model name for `saringan judge`. Required unless
#                         SARINGAN_SKIP_JUDGE=1.
#   SARINGAN_SKIP_JUDGE   Set to 1 to run deterministic validate only.
#   SARINGAN_CONFIG       Optional path to saringan.toml for validate.
#   SARINGAN_CONVENTIONS  Optional colon-separated file list, relative to worktree
#                         or absolute, included as judge conventions context.
#   SARINGAN_BASE_REF     Optional diff base ref. Default: origin/<prd_branch>.

set -u

# Default configuration for OpenCode Go + DeepSeek V4 Flash
# Prevents collision with Rangkai orchestrator's global Codex credentials
if [ "${OPENAI_BASE_URL:-}" = "https://gpt4.mirbuds.com/codex" ] || [ -z "${OPENAI_API_BASE:-}" ]; then
  export OPENAI_API_KEY="sk-eDSMCDZZTwGe08P1jvutImLNLz98tIhuLjeJBDh4tQsN4Ck5j9hjGYW5E31dfra7"
  export OPENAI_API_BASE="https://opencode.ai/zen/go/v1"
  export OPENAI_BASE_URL="https://opencode.ai/zen/go/v1"
fi
export SARINGAN_JUDGE_MODEL="${SARINGAN_JUDGE_MODEL:-openai/kimi-k2.6}"

emit_json() {
  local status="$1"
  local message="$2"
  python3 - "$status" "$message" <<'PY'
import json
import sys

print(json.dumps({"status": sys.argv[1], "message": sys.argv[2]}))
PY
}

fail_result() {
  emit_json "failed" "$1"
  exit 0
}

error_result() {
  emit_json "error" "$1"
  exit 0
}

if [ "$#" -lt 4 ]; then
  error_result "Usage: saringan-quality-gate.sh <worktree_path> <issue_number> <prd_branch> <implementation_branch>"
fi

WORKTREE_PATH="$1"
ISSUE_NUMBER="$2"
PRD_BRANCH="$3"
IMPLEMENTATION_BRANCH="$4"

SARINGAN_BIN="${SARINGAN_BIN:-saringan}"
SARINGAN_SKIP_JUDGE="${SARINGAN_SKIP_JUDGE:-0}"
BASE_REF="${SARINGAN_BASE_REF:-origin/$PRD_BRANCH}"

if [ ! -d "$WORKTREE_PATH" ]; then
  error_result "Worktree path does not exist: $WORKTREE_PATH"
fi

if ! command -v "$SARINGAN_BIN" >/dev/null 2>&1 && [ ! -x "$SARINGAN_BIN" ]; then
  # Fallback to local virtual environment path of saringan project or worktree
  if [ -x "/home/ungku/programming/saringan/.venv/bin/saringan" ]; then
    SARINGAN_BIN="/home/ungku/programming/saringan/.venv/bin/saringan"
  elif [ -x "$WORKTREE_PATH/.venv/bin/saringan" ]; then
    SARINGAN_BIN="$WORKTREE_PATH/.venv/bin/saringan"
  fi
fi

if ! command -v "$SARINGAN_BIN" >/dev/null 2>&1 && [ ! -x "$SARINGAN_BIN" ]; then
  error_result "Saringan executable not found: $SARINGAN_BIN"
fi

INPUT_DIR="$WORKTREE_PATH/quality-gate-inputs"
mkdir -p "$INPUT_DIR" || error_result "Could not create input directory: $INPUT_DIR"

DIFF_PATH="$INPUT_DIR/diff.patch"
ISSUE_PATH="$INPUT_DIR/issue.md"
CONVENTIONS_PATH="$INPUT_DIR/conventions.md"
VALIDATE_STDERR="$INPUT_DIR/validate.stderr"
JUDGE_STDERR="$INPUT_DIR/judge.stderr"

# Prepare diff against the PRD branch. Fetch failure is non-fatal because the
# branch may already exist locally or the repo may be intentionally offline.
git -C "$WORKTREE_PATH" fetch origin "$PRD_BRANCH" >/dev/null 2>&1 || true
if ! git -C "$WORKTREE_PATH" diff "$BASE_REF...HEAD" > "$DIFF_PATH" 2>"$INPUT_DIR/diff.stderr"; then
  # Fallback for shallow repos or missing merge-base. This still gives the judge
  # useful context and records why the preferred diff failed.
  if ! git -C "$WORKTREE_PATH" diff "$BASE_REF" > "$DIFF_PATH" 2>>"$INPUT_DIR/diff.stderr"; then
    error_result "Could not generate diff against $BASE_REF. See $INPUT_DIR/diff.stderr"
  fi
fi

# Prepare issue context. Prefer GitHub CLI; fall back to a minimal issue stub so
# deterministic validation can still run in local/offline scenarios.
if command -v gh >/dev/null 2>&1; then
  if ! gh issue view "$ISSUE_NUMBER" \
    --json title,body,url \
    --jq '"# " + .title + "\n\nIssue: " + .url + "\n\n" + (.body // "")' \
    > "$ISSUE_PATH" 2>"$INPUT_DIR/issue.stderr"; then
    {
      echo "# Issue #$ISSUE_NUMBER"
      echo
      echo "GitHub issue lookup failed. See $INPUT_DIR/issue.stderr."
    } > "$ISSUE_PATH"
  fi
else
  {
    echo "# Issue #$ISSUE_NUMBER"
    echo
    echo "GitHub CLI not available; issue body could not be fetched."
  } > "$ISSUE_PATH"
fi

# Prepare conventions/context for the judge. Keep this repository-local and
# deterministic: concatenate known docs if present, plus optional configured files.
: > "$CONVENTIONS_PATH"
append_context_file() {
  local candidate="$1"
  local resolved="$candidate"
  if [ "${candidate#/}" = "$candidate" ]; then
    resolved="$WORKTREE_PATH/$candidate"
  fi
  if [ -f "$resolved" ]; then
    {
      echo
      echo "# $candidate"
      cat "$resolved"
      echo
    } >> "$CONVENTIONS_PATH"
  fi
}

append_context_file "AGENTS.md"
append_context_file "CONTEXT.md"
append_context_file "CONVENTIONS.md"
append_context_file "README.md"

if [ -n "${SARINGAN_CONVENTIONS:-}" ]; then
  OLD_IFS="$IFS"
  IFS=":"
  for context_file in $SARINGAN_CONVENTIONS; do
    append_context_file "$context_file"
  done
  IFS="$OLD_IFS"
fi

# Run deterministic gate first. This is the blocking part of the quality gate.
VALIDATE_CMD=("$SARINGAN_BIN" "validate" "$WORKTREE_PATH" "--json")
if [ -n "${SARINGAN_CONFIG:-}" ]; then
  VALIDATE_CMD+=("--config" "$SARINGAN_CONFIG")
fi

VALIDATE_OUTPUT="$("${VALIDATE_CMD[@]}" 2>"$VALIDATE_STDERR")"
VALIDATE_EXIT=$?
printf '%s\n' "$VALIDATE_OUTPUT" > "$INPUT_DIR/validate.result.json"

if [ "$VALIDATE_EXIT" -ne 0 ]; then
  # Saringan validate uses non-zero for failed/error. Rangkai expects command
  # success plus status JSON to classify the gate, so forward stdout and exit 0.
  if [ -n "$VALIDATE_OUTPUT" ]; then
    printf '%s\n' "$VALIDATE_OUTPUT"
  else
    error_result "Saringan validate exited $VALIDATE_EXIT without stdout. See $VALIDATE_STDERR"
  fi
  exit 0
fi

VALIDATE_STATUS="$(printf '%s' "$VALIDATE_OUTPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "error"))' 2>/dev/null || printf 'error')"
if [ "$VALIDATE_STATUS" != "passed" ]; then
  printf '%s\n' "$VALIDATE_OUTPUT"
  exit 0
fi

if [ "$SARINGAN_SKIP_JUDGE" = "1" ]; then
  printf '%s\n' "$VALIDATE_OUTPUT"
  exit 0
fi

if [ -z "${SARINGAN_JUDGE_MODEL:-}" ]; then
  error_result "SARINGAN_JUDGE_MODEL is required for saringan judge, or set SARINGAN_SKIP_JUDGE=1."
fi

# Run advisory Contextual Judge Gate. Current Saringan semantics are advisory:
# if the judge completes, status is passed and evidence contains advisories,
# scope_guard, acceptance_criteria, and completion_score.
JUDGE_OUTPUT="$("$SARINGAN_BIN" judge "$WORKTREE_PATH" \
  --diff "$DIFF_PATH" \
  --issue "$ISSUE_PATH" \
  --conventions "$CONVENTIONS_PATH" \
  --model "$SARINGAN_JUDGE_MODEL" \
  --json 2>"$JUDGE_STDERR")"
JUDGE_EXIT=$?
printf '%s\n' "$JUDGE_OUTPUT" > "$INPUT_DIR/judge.result.json"

if [ "$JUDGE_EXIT" -ne 0 ]; then
  if [ -n "$JUDGE_OUTPUT" ]; then
    printf '%s\n' "$JUDGE_OUTPUT"
  else
    error_result "Saringan judge exited $JUDGE_EXIT without stdout. See $JUDGE_STDERR"
  fi
  exit 0
fi

printf '%s\n' "$JUDGE_OUTPUT"
exit 0
