#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# bazel_diff.sh — Computes affected Bazel targets between two git refs and
#                 runs only their tests. Wraps the bazel-diff CLI tool.
#
# Usage:
#   ./scripts/bazel_diff.sh [BASE_REF] [HEAD_REF]
#
# Defaults:
#   BASE_REF = origin/main
#   HEAD_REF = HEAD
#
# Requirements:
#   - bazel-diff JAR on PATH or at $BAZEL_DIFF_JAR
#   - Bazel 8 in PATH
#   - git in PATH
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_REF="${1:-origin/main}"
HEAD_REF="${2:-HEAD}"
BAZEL_DIFF_JAR="${BAZEL_DIFF_JAR:-$(which bazel-diff 2>/dev/null || echo '')}"
WORKSPACE_DIR="$(git rev-parse --show-toplevel)"
TMP_DIR="$(mktemp -d)"

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "$BAZEL_DIFF_JAR" ]]; then
  echo "ERROR: bazel-diff not found. Install via:"
  echo "  curl -Lo /usr/local/bin/bazel-diff \\"
  echo "    https://github.com/Tinder/bazel-diff/releases/latest/download/bazel-diff_deploy.jar"
  echo "  chmod +x /usr/local/bin/bazel-diff"
  exit 1
fi

echo "── Amanah bazel-diff ────────────────────────────────────────────────────"
echo "  BASE : $BASE_REF"
echo "  HEAD : $HEAD_REF"
echo "  TMP  : $TMP_DIR"
echo ""

BASE_HASHES="$TMP_DIR/base_hashes.json"
HEAD_HASHES="$TMP_DIR/head_hashes.json"
IMPACTED="$TMP_DIR/impacted_targets.txt"

# ── Generate hashes for BASE commit ───────────────────────────────────────────
echo "[1/4] Generating hashes for $BASE_REF …"
git stash --include-untracked --quiet 2>/dev/null || true
git checkout "$BASE_REF" --quiet 2>/dev/null || true

bazel-diff generate-hashes \
  --workspacePath="$WORKSPACE_DIR" \
  --bazelPath="$(which bazel)" \
  --output="$BASE_HASHES"

# ── Restore HEAD ──────────────────────────────────────────────────────────────
echo "[2/4] Restoring $HEAD_REF …"
git checkout - --quiet 2>/dev/null || true
git stash pop --quiet 2>/dev/null || true

# ── Generate hashes for HEAD ──────────────────────────────────────────────────
echo "[3/4] Generating hashes for $HEAD_REF …"
bazel-diff generate-hashes \
  --workspacePath="$WORKSPACE_DIR" \
  --bazelPath="$(which bazel)" \
  --output="$HEAD_HASHES"

# ── Compute impacted targets ──────────────────────────────────────────────────
echo "[4/4] Computing impacted targets …"
bazel-diff get-impacted-targets \
  --startingHashes="$BASE_HASHES" \
  --finalHashes="$HEAD_HASHES" \
  --output="$IMPACTED"

IMPACTED_COUNT=$(wc -l < "$IMPACTED" | tr -d ' ')
echo ""
echo "── Impacted targets ($IMPACTED_COUNT) ───────────────────────────────────"
cat "$IMPACTED"

if [[ "$IMPACTED_COUNT" -eq 0 ]]; then
  echo "No targets affected. Skipping tests."
  exit 0
fi

# ── Run tests for impacted targets only ───────────────────────────────────────
echo ""
echo "── Running tests for impacted targets …"
# Filter to test targets only (exclude binary/library targets from test run)
TEST_TARGETS=$(grep -E "_test$|Tests$|test$" "$IMPACTED" || true)

if [[ -z "$TEST_TARGETS" ]]; then
  echo "No test targets in impacted set."
else
  # shellcheck disable=SC2086
  bazel test $TEST_TARGETS --keep_going
fi

echo ""
echo "── Done. Cleaning up $TMP_DIR …"
rm -rf "$TMP_DIR"
