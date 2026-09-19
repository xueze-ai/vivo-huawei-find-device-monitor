#!/bin/bash
set -euo pipefail
umask 077
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
xvfb_pid=$!
cleanup() {
  if [ -n "${app_pid:-}" ]; then
    kill -TERM "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
  fi
  kill $(jobs -pr) 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' TERM INT
for i in {1..50}; do
  [ -S /tmp/.X11-unix/X99 ] && break
  sleep 0.1
done
x11vnc -display :99 -localhost -forever -shared -nopw -rfbport 5900 >/dev/null 2>&1 &
websockify --web=/usr/share/novnc/ 6080 localhost:5900 >/dev/null 2>&1 &
app_dir="${APP_DIR:-/app/vivo}"
if [ "${1:-monitor}" = login ]; then
  python "$app_dir/login.py" &
else
  python "$app_dir/monitor.py" &
fi
app_pid=$!
wait "$app_pid"
