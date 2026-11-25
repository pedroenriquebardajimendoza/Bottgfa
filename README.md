# 📬 Programador de mensajes para Telegram

Envía mensajes automáticamente a tus grupos **desde tu propia cuenta** (aparecen como
enviados por ti, no por un bot), y contrólalo todo desde un bot de Telegram:

- ➕ Crear varios mensajes programados
- 📝 Editar el texto en cualquier momento (con negrita, cursiva, enlaces, spoilers, emojis…) o poner una **foto con texto**
- 👥 Elegir a qué grupos va cada mensaje (lista con casillas ✅)
- ⏱ Elegir cada cuánto se envía (15 min, 1 h, 24 h… o lo que escribas: `45`, `2h`, `1h30m`, `1d`)
- ▶️ Activar / ⏸ pausar, 🚀 enviar ya, 👁 vista previa
- 🔒 Solo tú (tu ID) puedes usar el bot

## ¿Cómo funciona?

| Pieza | Para qué sirve |
|---|---|
| **Bot de control** (lo creas con @BotFather) | Es el "panel": le escribes y te muestra menús con botones. |
| **Tu cuenta** (sesión con Telethon) | Es la que publica en los grupos, por eso sale tu nombre. |
| `bot.py` | El programa. Une las dos cosas y envía cuando toca. |

> Un bot normal de Telegram **no puede** publicar como si fueras tú; por eso se usa tu cuenta
> mediante la API oficial de Telegram (MTProto).

---

## 1. Datos que necesitas

1. **API ID y API HASH**: entra en <https://my.telegram.org> con tu número →
   *API development tools* → crea una app (nombre y descripción cualquiera) → copia `api_id` y `api_hash`.
2. **Token del bot**: en Telegram habla con **@BotFather** → `/newbot` → copia el token.
3. **Tu ID**: habla con **@userinfobot** y te dice tu ID numérico.
4. **Abre tu bot y pulsa *Iniciar*** (si no, el bot no puede escribirte).

## 2. Instalar en tu VPS de HostGator (Ubuntu) — recomendado

1. En el panel de HostGator pulsa **Abrir consola** (o conéctate por SSH: `ssh root@IP_DE_TU_VPS`).
2. Copia y pega:
   ```bash
   apt-get update && apt-get install -y git python3-pip
   cd ~ && git clone https://github.com/pedroenriquebardajimendoza/Bottgfa.git bottgfa
   cd bottgfa && git checkout claude/gracious-gauss-nmkjt5
   bash instalar.sh
   ```
   Si el repositorio es privado, GitHub te pedirá usuario y un *token* (GitHub → Settings →
   Developer settings → Personal access tokens) en lugar de la contraseña.
3. Responde lo que te pide (datos de Telegram, tu número y el código). Al final el bot queda
   funcionando **24/7 como servicio** y se reinicia solo si el VPS se reinicia.
4. Escribe `/start` a tu bot. ✅

Comandos útiles: `systemctl status bottgfa` (estado) · `systemctl restart bottgfa` (reiniciar) ·
`tail -f ~/bottgfa/bot.log` (registro) · `python3 bot.py --check` (diagnóstico).

### Alternativa: hosting compartido (sin VPS, con cron)

1. En **cPanel → Terminal** (o por SSH):
   ```bash
   cd ~ && git clone https://github.com/pedroenriquebardajimendoza/Bottgfa.git bottgfa && cd bottgfa
   ```
   (Sin git: sube los archivos con el Administrador de archivos a `~/bottgfa`, **fuera de `public_html`**.)
2. Ejecuta el instalador y responde lo que te pida:
   ```bash
   bash instalar.sh
   ```
   Instala Telethon, crea `config.ini`, inicia sesión con tu cuenta (número + código de Telegram),
   **comprueba que todo conecta** y deja programado el cron cada minuto.
3. Escribe `/start` a tu bot. ✅

Si el instalador no pudo crear el cron, añádelo en **cPanel → Cron Jobs** con la línea que te muestra.
Si tu plan no permite cron cada minuto, usa cada 15 min con `bot.py --cron 870`
(el instalador te muestra la línea exacta).

Comprobar en cualquier momento que todo funciona: `python3 bot.py --check`

> ⚠️ **`cuenta.session` y `config.ini` dan acceso a tu cuenta. No los compartas ni los subas a GitHub**
> (ya están en `.gitignore`).

## 3. Uso

1. `/start` → **🔄 Actualizar lista de grupos** (lee los grupos de tu cuenta).
2. **➕ Nuevo mensaje** → envía el texto (o una foto con texto).
3. **👥 Grupos** → marca los grupos ✅ → **Listo**.
4. **⏱ Intervalo** → elige cada cuánto.
5. **▶️ Activar** → se envía en breve y después cada X tiempo.

Para cambiar el texto más tarde: **📋 Mis mensajes** → el mensaje → **📝 Editar texto**.
Comandos: `/start` o `/menu` (menú), `/cancelar` (cancelar lo que estés escribiendo), `/id`.

Los registros quedan en `bot.log`. La configuración de los mensajes se guarda en `data.json`.

## 4. Recomendaciones para no tener problemas con Telegram

- Úsalo **solo en tus grupos** o donde tengas permiso para publicar.
- No pongas intervalos muy cortos con muchos grupos; Telegram puede limitar o banear cuentas que
  hacen spam. El bot ya deja una pausa aleatoria entre grupo y grupo (`pausa_min` / `pausa_max`)
  y respeta los avisos de "espera" de Telegram.
- Si cambias la contraseña o cierras todas las sesiones de tu cuenta, vuelve a ejecutar `python3 login.py`.

## 5. Problemas frecuentes

| Problema | Solución |
|---|---|
| El bot no responde | Ejecuta `python3 bot.py --check`. Revisa `bot.log`, el cron y que `admin_id` es tu ID. |
| `--check` da error de conexión | HostGator bloquea la salida a Telegram: pide a soporte que abran `api.telegram.org` y el puerto 443 saliente, o usa un VPS. |
| "La cuenta no ha iniciado sesión" | Ejecuta `python3 login.py` en la carpeta del bot. |
| No aparece un grupo | Pulsa **🔄 Actualizar grupos**. Tu cuenta debe estar dentro del grupo. |
| Falla en un grupo concreto | Puede que el grupo no permita escribir (solo admins, modo lento…). |
| Error al instalar Telethon | Usa `python3 -m pip install --user --upgrade pip` y vuelve a intentarlo. |
