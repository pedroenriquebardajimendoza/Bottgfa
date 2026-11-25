#!/bin/bash
# Instalador: ejecuta  bash instalar.sh  dentro de la carpeta del bot.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && { echo "No encuentro python3. Pide a HostGator que lo activen."; exit 1; }
echo "== 1/5 Instalando librería (Telethon) =="
if [ "$(id -u)" = "0" ] && command -v apt-get >/dev/null && ! "$PY" -m pip --version >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq python3-pip
fi
"$PY" -m pip install --user -q -r requirements.txt 2>/dev/null || "$PY" -m pip install -q -r requirements.txt 2>/dev/null || pip3 install --user -q -r requirements.txt

if [ ! -f config.ini ]; then
  echo "== 2/5 Configuración =="
  echo "(api_id y api_hash: https://my.telegram.org | token: @BotFather | tu ID: @userinfobot)"
  read -rp "api_id: " API_ID
  set -- $API_ID
  if [ $# -ge 4 ]; then  # pegó los 4 datos en una sola línea
    API_ID=$1; API_HASH=$2; TOKEN=$3; ADMIN=$4
  else
    read -rp "api_hash: " API_HASH
    read -rp "Token del bot: " TOKEN
    read -rp "Tu ID de Telegram: " ADMIN
  fi
  for v in "$API_ID" "$ADMIN"; do
    case "$v" in ''|*[!0-9]*) echo "❌ api_id y tu ID deben ser solo números. Vuelve a ejecutar: bash instalar.sh"; exit 1;; esac
  done
  sed -e "s|^api_id = .*|api_id = $API_ID|" -e "s|^api_hash = .*|api_hash = $API_HASH|" \
      -e "s|^bot_token = .*|bot_token = $TOKEN|" -e "s|^admin_id = .*|admin_id = $ADMIN|" \
      config.example.ini > config.ini
  chmod 600 config.ini
else
  echo "== 2/5 config.ini ya existe, lo uso =="
fi

echo "== 3/5 Inicio de sesión con tu cuenta =="
ls ./*.session >/dev/null 2>&1 && echo "Sesión ya existente." || "$PY" login.py
chmod 600 ./*.session 2>/dev/null || true

echo "== 4/5 Diagnóstico =="
"$PY" bot.py --check

if [ "$(id -u)" = "0" ] && command -v systemctl >/dev/null; then
  echo "== 5/5 Servicio 24/7 (VPS) =="
  cat > /etc/systemd/system/bottgfa.service <<SVC
[Unit]
Description=Bot programador de mensajes de Telegram
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$PY $DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVC
  (crontab -l 2>/dev/null | grep -v "bot.py --cron") | crontab - 2>/dev/null || true
  systemctl daemon-reload
  systemctl enable --now bottgfa
  systemctl restart bottgfa
  echo "✅ Bot funcionando 24/7. Escribe /start a tu bot."
  echo "   Ver estado: systemctl status bottgfa   |   Ver registro: tail -f $DIR/bot.log"
  exit 0
fi

echo "== 5/5 Cron =="
LINE="* * * * * cd $DIR && $PY bot.py --cron >/dev/null 2>&1"
if command -v crontab >/dev/null && (crontab -l 2>/dev/null | grep -v "bot.py --cron"; echo "$LINE") | crontab - 2>/dev/null; then
  echo "✅ Cron instalado (cada minuto). Escribe /start a tu bot."
else
  echo "No pude instalar el cron automáticamente. En cPanel > Cron Jobs añade (cada minuto):"
  echo "  $LINE"
fi
echo "Si tu plan solo permite cron cada 15 min, usa: */15 * * * * cd $DIR && $PY bot.py --cron 870 >/dev/null 2>&1"
