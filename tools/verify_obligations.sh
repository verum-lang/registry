#!/usr/bin/env bash
# Preserve the existing entry point. The companion owns source/result
# accounting, process deadlines and cleanup of its own temporary directory.
# Exit 0: all obligations proved; 1: measured open obligations;
# 2: setup, invocation, report or coverage failure.
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/verify_obligations.py" "$@"
