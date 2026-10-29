#!/usr/bin/env bash
# Installs Kitchen Hub on a Raspberry Pi: dependencies, the server as a systemd service, and the
# touchscreen app at desktop login. Safe to run again after a `git pull`.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(id -un)"
cd "$APP_DIR"

echo "==> System packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-kivy curl
# Prebuilt copies of the compiled dependencies; building them from source on a Pi Zero takes hours.
for pkg in python3-pydantic python3-cryptography python3-cffi python3-rpds-py; do
  sudo apt-get install -y "$pkg" || echo "   No $pkg package; pip will try instead."
done

echo "==> Python packages"
[ -d venv ] || python3 -m venv --system-site-packages venv
if ! venv/bin/pip install --prefer-binary -r requirements.txt; then
  echo "==> Full install failed. Installing without the MCP server (touchscreen and phone still work)."
  sudo apt-get install -y python3-fastapi python3-uvicorn python3-dotenv python3-qrcode
fi

echo "==> Settings"
if [ ! -f .env ]; then
  cp .env.example .env
  token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^KITCHEN_TOKEN=.*|KITCHEN_TOKEN=$token|" .env
  echo "   Created .env with a new token. Add KITCHEN_COOKS and KITCHEN_PUBLIC_URL to it."
fi
chmod 600 .env

echo "==> Server service"
sed -e "s|@USER@|$APP_USER|g" -e "s|@DIR@|$APP_DIR|g" deploy/kitchen-hub-api.service |
  sudo tee /etc/systemd/system/kitchen-hub-api.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable kitchen-hub-api
sudo systemctl restart kitchen-hub-api

echo "==> Touchscreen app at login"
chmod +x deploy/kitchen-hub-ui.sh
mkdir -p "$HOME/.config/autostart"
sed "s|@DIR@|$APP_DIR|g" deploy/kitchen-hub-ui.desktop > "$HOME/.config/autostart/kitchen-hub-ui.desktop"

echo "==> Checking the server"
for _ in $(seq 1 30); do
  curl -fs -o /dev/null http://127.0.0.1:8000/docs && break
  sleep 2
done
if curl -fs -o /dev/null http://127.0.0.1:8000/docs; then
  echo "   Server is up."
  echo "Done. Reboot to check that everything starts on its own: sudo reboot"
else
  echo "   Server didn't start. See: journalctl -u kitchen-hub-api -n 50"
  exit 1
fi
