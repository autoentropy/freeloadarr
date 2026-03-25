#!/bin/sh
set -eu

DB_PATH="${DB_PATH:-/config/freeloadarr.db}"
WEBUI_HOST="${WEBUI_HOST:-0.0.0.0}"
WEBUI_PORT="${WEBUI_PORT:-11012}"
DETECTOR_SCRIPT="${DETECTOR_SCRIPT:-/config/freeloadarr_detector.py}"
WEBUI_SCRIPT="${WEBUI_SCRIPT:-/config/freeloadarr_webui.py}"

export DB_PATH WEBUI_HOST WEBUI_PORT

if [ ! -f "$DETECTOR_SCRIPT" ]; then
  echo "ERROR: Detector script not found at $DETECTOR_SCRIPT"
  exit 1
fi

if [ ! -f "$WEBUI_SCRIPT" ]; then
  echo "ERROR: Web UI script not found at $WEBUI_SCRIPT"
  exit 1
fi

cleanup() {
  echo "Stopping Freeloadarr..."
  [ -n "${DETECTOR_PID:-}" ] && kill "$DETECTOR_PID" 2>/dev/null || true
  [ -n "${WEBUI_PID:-}" ] && kill "$WEBUI_PID" 2>/dev/null || true
  wait "$DETECTOR_PID" 2>/dev/null || true
  wait "$WEBUI_PID" 2>/dev/null || true
}

trap cleanup INT TERM

echo "Starting Freeloadarr detector..."
python "$DETECTOR_SCRIPT" &
DETECTOR_PID=$!

echo "Starting Freeloadarr web UI on port $WEBUI_PORT..."
python "$WEBUI_SCRIPT" &
WEBUI_PID=$!

while true; do
  if ! kill -0 "$DETECTOR_PID" 2>/dev/null; then
    echo "Detector exited; stopping container."
    kill "$WEBUI_PID" 2>/dev/null || true
    wait "$WEBUI_PID" 2>/dev/null || true
    exit 1
  fi

  if ! kill -0 "$WEBUI_PID" 2>/dev/null; then
    echo "Web UI exited; stopping container."
    kill "$DETECTOR_PID" 2>/dev/null || true
    wait "$DETECTOR_PID" 2>/dev/null || true
    exit 1
  fi

  sleep 5
done
