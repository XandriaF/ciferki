#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите так: sudo bash deploy/update.sh"
  exit 1
fi

echo "== Обновление кода =="
cd /opt/ciferki
git -c safe.directory=/opt/ciferki pull --ff-only

echo "== Зависимости =="
.venv/bin/pip install --quiet -r requirements.txt
chown -R ciferki:ciferki /opt/ciferki

echo "== Перезапуск сервиса =="
systemctl restart ciferki
systemctl --no-pager status ciferki | head -n 12 || true
