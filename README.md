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

## 2. Instalar en HostGator (hosting compartido)

### 2.1 Activar SSH / Terminal
En **cPanel** busca **Terminal** (o activa el acceso **SSH** desde el portal de HostGator).
Todo lo siguiente se escribe ahí.

### 2.2 Subir los archivos
Opción A — con git (si está disponible):
```bash
cd ~
git clone https://github.com/pedroenriquebardajimendoza/Bottgfa.git bottgfa
cd bottgfa
```
Opción B — sube los archivos (`bot.py`, `login.py`, `config.example.ini`, `requirements.txt`)
con el **Administrador de archivos** de cPanel a una carpeta `bottgfa` **fuera de `public_html`**
(así nadie puede descargarlos desde la web).

### 2.3 Instalar la librería
```bash
cd ~/bottgfa
python3 --version          # necesitas 3.6 o superior
python3 -m pip install --user -r requirements.txt
```
Si `pip` no existe, prueba con `pip3 install --user telethon`.

### 2.4 Configurar
```bash
cp config.example.ini config.ini
nano config.ini            # pon api_id, api_hash, bot_token y admin_id
chmod 600 config.ini
```

### 2.5 Iniciar sesión con tu cuenta (solo una vez)
```bash
python3 login.py
```
Te pedirá tu número (con prefijo, ej. `+34600111222`), el código que te llega por Telegram y
tu contraseña de dos pasos si la tienes. Se crea el archivo `cuenta.session`.

> ⚠️ **`cuenta.session` y `config.ini` dan acceso a tu cuenta. No los compartas ni los subas a GitHub**
> (ya están en `.gitignore`).

### 2.6 Probar
```bash
python3 bot.py
```
Escribe `/start` a tu bot: debe responder con el menú. Para pararlo pulsa `Ctrl + C`.

### 2.7 Dejarlo funcionando siempre (cron)
Los hostings compartidos cierran los programas que se quedan abiertos, así que se usa **cron**:
el bot se ejecuta cada minuto, trabaja ~55 segundos y se cierra (nunca se ejecutan dos a la vez).

En **cPanel → Trabajos de cron (Cron Jobs)** añade uno con la configuración
**"Una vez por minuto" (`* * * * *`)** y este comando (cambia `TUUSUARIO` por tu usuario de cPanel):

```
cd /home/TUUSUARIO/bottgfa && /usr/bin/python3 bot.py --cron >/dev/null 2>&1
```

> Puedes ver la ruta exacta con `pwd` (dentro de la carpeta) y `which python3`.
> Si tu plan no permite cron cada minuto, el bot funcionará igual pero responderá más lento.

¡Listo! Ya puedes gestionarlo todo desde el bot.

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
| El bot no responde | Revisa `bot.log`. Comprueba que el cron está bien y que `admin_id` es tu ID. |
| "La cuenta no ha iniciado sesión" | Ejecuta `python3 login.py` en la carpeta del bot. |
| No aparece un grupo | Pulsa **🔄 Actualizar grupos**. Tu cuenta debe estar dentro del grupo. |
| Falla en un grupo concreto | Puede que el grupo no permita escribir (solo admins, modo lento…). |
| Error al instalar Telethon | Usa `python3 -m pip install --user --upgrade pip` y vuelve a intentarlo. |
