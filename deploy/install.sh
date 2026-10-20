#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/grigory-bot
cd "$APP_DIR"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запустите install.sh от root" >&2
  exit 1
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "Создайте $APP_DIR/.env с BOT_TOKEN и ADMIN_USERNAMES" >&2
  exit 1
fi
chmod 600 "$APP_DIR/.env"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip ca-certificates

if ! id -u bot >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin bot
fi

mkdir -p "$APP_DIR/data"
chown -R bot:bot "$APP_DIR"

runuser -u bot -- python3 -m venv "$APP_DIR/.venv"
runuser -u bot -- "$APP_DIR/.venv/bin/pip" install --upgrade pip
runuser -u bot -- "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

cp "$APP_DIR/deploy/grigory-bot.service" /etc/systemd/system/grigory-bot.service
systemctl daemon-reload
systemctl enable grigory-bot
systemctl restart grigory-bot
sleep 2
systemctl --no-pager --full status grigory-bot
