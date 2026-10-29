#!/usr/bin/env bash
# Started at desktop login. Waits for the server, then keeps the touchscreen app running (restarts it if it crashes).
cd "$(dirname "$0")/.."
exec > "$HOME/.kitchen-hub-ui.log" 2>&1

for _ in $(seq 1 60); do
  curl -fs -o /dev/null http://127.0.0.1:8000/docs && break
  sleep 2
done

while true; do
  venv/bin/python -m ui.main
  echo "Touchscreen app exited with code $?; restarting in 3 seconds"
  sleep 3
done
