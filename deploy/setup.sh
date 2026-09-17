#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите так: sudo bash deploy/setup.sh [домен]"
  exit 1
fi

echo "== 1/6. Пакеты =="
apt-get update -y
apt-get install -y python3-venv nginx git

echo "== 2/6. Пользователь сервиса =="
if ! id ciferki >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin ciferki
fi

echo "== 3/6. Код =="
if [ -d /opt/ciferki/.git ]; then
  git -C /opt/ciferki -c safe.directory=/opt/ciferki pull --ff-only
else
  git clone https://github.com/XandriaF/ciferki.git /opt/ciferki
fi

echo "== 4/6. Python-окружение =="
cd /opt/ciferki
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
chown -R ciferki:ciferki /opt/ciferki

echo "== 5/6. Автозапуск (systemd) =="
sed "s/CHANGE_ME/ciferki/g" deploy/ciferki.service > /etc/systemd/system/ciferki.service
systemctl daemon-reload
systemctl enable ciferki
systemctl restart ciferki

echo "== 6/6. Nginx =="
if [ -n "$DOMAIN" ]; then
  sed "s/ciferki.example.ru/${DOMAIN}/" deploy/nginx.conf > /etc/nginx/sites-available/ciferki
else
  sed -e "s/ciferki.example.ru/_/" -e "s/listen 80;/listen 8080;/" deploy/nginx.conf > /etc/nginx/sites-available/ciferki
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow 8080/tcp
  fi
fi
ln -sf /etc/nginx/sites-available/ciferki /etc/nginx/sites-enabled/ciferki
nginx -t
systemctl reload nginx

echo
echo "=============================="
systemctl --no-pager status ciferki | head -n 10 || true
echo "=============================="
echo -n "Проверка health: "
curl -s http://127.0.0.1:8000/health || true
echo
if [ -n "$DOMAIN" ]; then
  echo "Сервис доступен: http://${DOMAIN}"
  echo "Для HTTPS выполните: apt-get install -y certbot python3-certbot-nginx && certbot --nginx -d ${DOMAIN}"
else
  echo "Сервис доступен: http://72.56.242.246:8080"
fi
