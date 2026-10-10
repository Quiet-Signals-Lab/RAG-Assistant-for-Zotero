#!/bin/bash
# Shell wrapper to fully detach the Python backend from the Electron process tree.
# This avoids Chromium sandbox restrictions that can kill child Python processes.
#
# Logs go to $RAG_LOG_DIR (Electron passes its user data "logs" folder) so they
# survive reboots and are not overwritten on every launch. /tmp is the fallback
# when the wrapper is run by hand.

LOG_DIR="${RAG_LOG_DIR:-/tmp}"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
LOG="$LOG_DIR/backend-shell-wrapper.log"

# Keep one previous generation once the log passes 10 MB.
if [ -f "$BACKEND_LOG" ] && [ "$(stat -c %s "$BACKEND_LOG" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    mv -f "$BACKEND_LOG" "$BACKEND_LOG.1"
fi

{
    echo "=== Shell wrapper started ==="
    echo "PID: $$"
    echo "PPID: $PPID"
    echo "Args: $@"
    date

    echo "" >> "$BACKEND_LOG"
    echo "[wrapper] backend starting at $(date -Is)" >> "$BACKEND_LOG"

    # Fully detach using setsid and nohup: a new session and process group
    # completely independent of Electron. stdout and stderr share one file so
    # tracebacks stay in order with the lines around them.
    setsid nohup "$@" >> "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!

    echo "Backend launched with PID: $BACKEND_PID"
    echo "Backend log: $BACKEND_LOG"

    # PID file so Electron can track it
    echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"

} >> "$LOG" 2>&1

# Exit immediately - backend is fully detached
exit 0
