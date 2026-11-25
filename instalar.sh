#!/bin/bash
# Instalador: ejecuta  bash instalar.sh  dentro de la carpeta del bot.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && { echo "No encuentro python3. Pide a HostGator que lo activen."; exit 1; }
echo "== 1/5 Instalando librería (Telethon) =="
"$PY" -m pip install --user -q -r requirements.txt 2>/dev/null || "$PY" -m pip install -q -r requirements.txt 2>/dev/null || pip3 install --user -q -r requirements.txt

if [ ! -f config.ini ]; then
  echo "== 2/5 Configuración =="
  echo "(api_id y api_hash: https://my.telegram.org | token: @BotFather | tu ID: @userinfobot)"
  read -rp "api_id: " API_ID
  read -rp "api_hash: " API_HASH
  read -rp "Token del bot: " TOKEN
  read -rp "Tu ID de Telegram: " ADMIN
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

echo "== 5/5 Cron =="
LINE="* * * * * cd $DIR && $PY bot.py --cron >/dev/null 2>&1"
if command -v crontab >/dev/null && (crontab -l 2>/dev/null | grep -v "bot.py --cron"; echo "$LINE") | crontab - 2>/dev/null; then
  echo "✅ Cron instalado (cada minuto). Escribe /start a tu bot."
else
  echo "No pude instalar el cron automáticamente. En cPanel > Cron Jobs añade (cada minuto):"
  echo "  $LINE"
fi
echo "Si tu plan solo permite cron cada 15 min, usa: */15 * * * * cd $DIR && $PY bot.py --cron 870 >/dev/null 2>&1"
