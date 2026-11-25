#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Programador de mensajes para Telegram.

- Un BOT (creado con @BotFather) hace de panel de control: desde él creas
  mensajes, editas el texto, eliges los grupos y el intervalo de envío.
- Tu CUENTA personal (userbot con Telethon) es la que envía los mensajes,
  así que en los grupos aparecen como enviados por ti.

Modos de ejecución:
    python3 bot.py           -> modo continuo (VPS / servidor propio)
    python3 bot.py --cron    -> modo cron: trabaja ~55 s y termina.
                                Pensado para hosting compartido (HostGator)
                                ejecutándolo cada minuto con cron.
"""
import asyncio
import configparser
import functools
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

try:
    import fcntl
except ImportError:  # Windows: sin bloqueo de archivo
    fcntl = None

from telethon import TelegramClient, errors, types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')
DATA_PATH = os.path.join(BASE_DIR, 'data.json')
LOCK_PATH = os.path.join(BASE_DIR, 'bot.lock')
LOG_PATH = os.path.join(BASE_DIR, 'bot.log')
MEDIA_DIR = os.path.join(BASE_DIR, 'media')

GROUPS_PER_PAGE = 8

log = logging.getLogger('programador')


# ---------------------------------------------------------------------------
# Configuración y almacenamiento
# ---------------------------------------------------------------------------

def load_config():
    cp = configparser.ConfigParser()
    if not cp.read(CONFIG_PATH, encoding='utf-8'):
        sys.exit('No encuentro config.ini. Copia config.example.ini a config.ini y rellénalo.')
    tg = cp['telegram']
    env = cp['envio'] if cp.has_section('envio') else {}
    return {
        'api_id': int(tg['api_id']),
        'api_hash': tg['api_hash'].strip(),
        'bot_token': tg['bot_token'].strip(),
        'admin_id': int(tg['admin_id']),
        'session': os.path.join(BASE_DIR, tg.get('session', 'cuenta').strip()),
        'pause_min': float(env.get('pausa_min', '4')),
        'pause_max': float(env.get('pausa_max', '10')),
        'notify': env.get('notificar_envios', 'si').strip().lower() in ('si', 'sí', 'yes', 'true', '1'),
    }


def default_data():
    return {
        'next_id': 1,
        'messages': {},       # id -> mensaje programado
        'groups': {},         # id de grupo (str) -> título
        'groups_updated': 0,
        'state': None,        # qué está esperando el bot (texto, intervalo...)
        'update_offset': 0,   # último update procesado de la Bot API
    }


def load_data():
    if not os.path.exists(DATA_PATH):
        return default_data()
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    base = default_data()
    base.update(data)
    return base


def save_data(data):
    tmp = DATA_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_PATH)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def parse_interval(text):
    """'30' -> 30 min, '45m', '2h', '1d', '1h30m' -> minutos. None si no es válido."""
    t = text.strip().lower().replace(' ', '')
    if re.fullmatch(r'\d+', t):
        minutes = int(t)
    else:
        parts = re.findall(r'(\d+)([dhm])', t)
        if not parts or ''.join(n + u for n, u in parts) != t:
            return None
        mult = {'d': 1440, 'h': 60, 'm': 1}
        minutes = sum(int(n) * mult[u] for n, u in parts)
    if minutes < 1 or minutes > 60 * 24 * 60:
        return None
    return minutes


def fmt_interval(minutes):
    d, rest = divmod(minutes, 1440)
    h, m = divmod(rest, 60)
    out = []
    if d:
        out.append('%d d' % d)
    if h:
        out.append('%d h' % h)
    if m:
        out.append('%d min' % m)
    return ' '.join(out) or '0 min'


def fmt_remaining(seconds):
    if seconds <= 0:
        return 'ahora mismo'
    minutes = int((seconds + 59) // 60)
    return 'en ' + fmt_interval(minutes)


def to_telethon_entities(entities):
    """Convierte las entities de la Bot API en entities de Telethon (MTProto).
    Ambas usan offsets en unidades UTF-16, así que el formato se conserva tal cual."""
    out = []
    simple = {
        'bold': types.MessageEntityBold,
        'italic': types.MessageEntityItalic,
        'underline': types.MessageEntityUnderline,
        'strikethrough': types.MessageEntityStrike,
        'spoiler': types.MessageEntitySpoiler,
        'code': types.MessageEntityCode,
        'url': types.MessageEntityUrl,
        'mention': types.MessageEntityMention,
        'hashtag': types.MessageEntityHashtag,
        'cashtag': types.MessageEntityCashtag,
        'bot_command': types.MessageEntityBotCommand,
        'email': types.MessageEntityEmail,
        'phone_number': types.MessageEntityPhone,
    }
    for e in entities or []:
        t, o, l = e.get('type'), e['offset'], e['length']
        if t in simple:
            out.append(simple[t](o, l))
        elif t == 'pre':
            out.append(types.MessageEntityPre(o, l, e.get('language', '')))
        elif t == 'text_link':
            out.append(types.MessageEntityTextUrl(o, l, e['url']))
        elif t == 'custom_emoji':
            out.append(types.MessageEntityCustomEmoji(o, l, int(e['custom_emoji_id'])))
        elif t == 'blockquote':
            out.append(types.MessageEntityBlockquote(o, l))
        elif t == 'expandable_blockquote':
            out.append(types.MessageEntityBlockquote(o, l, collapsed=True))
    return out


def kb(rows):
    return {'inline_keyboard': [[{'text': t, 'callback_data': d} for t, d in row] for row in rows]}


# ---------------------------------------------------------------------------
# Bot API (panel de control) — HTTP simple, sin dependencias extra
# ---------------------------------------------------------------------------

class BotAPIError(Exception):
    pass


class BotAPI:
    def __init__(self, token):
        self.base = 'https://api.telegram.org/bot%s/' % token
        self.file_base = 'https://api.telegram.org/file/bot%s/' % token

    def call(self, method, _http_timeout=30, **params):
        data = json.dumps(params).encode('utf-8')
        req = urllib.request.Request(self.base + method, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=_http_timeout) as r:
                res = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            try:
                res = json.loads(e.read().decode('utf-8'))
            except Exception:
                raise BotAPIError('HTTP %s' % e.code)
        if not res.get('ok'):
            raise BotAPIError(res.get('description', 'error desconocido'))
        return res['result']

    def download(self, file_path, dest):
        with urllib.request.urlopen(self.file_base + file_path, timeout=120) as r, open(dest, 'wb') as f:
            f.write(r.read())


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------

class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.admin = cfg['admin_id']
        self.bot = BotAPI(cfg['bot_token'])
        self.data = load_data()
        self.client = None

    # ---------- helpers asíncronos ----------

    async def api(self, method, _http_timeout=30, **params):
        loop = asyncio.get_event_loop()
        fn = functools.partial(self.bot.call, method, _http_timeout=_http_timeout, **params)
        return await loop.run_in_executor(None, fn)

    async def send(self, text, markup=None, chat_id=None):
        params = {'chat_id': chat_id or self.admin, 'text': text, 'parse_mode': 'HTML',
                  'disable_web_page_preview': True}
        if markup:
            params['reply_markup'] = markup
        try:
            return await self.api('sendMessage', **params)
        except BotAPIError as e:
            log.warning('No pude enviar mensaje por el bot: %s', e)

    async def show(self, view, message_id=None):
        """Muestra una pantalla (texto, teclado). Edita el mensaje si se pasa message_id."""
        text, markup = view
        if message_id:
            try:
                params = {'chat_id': self.admin, 'message_id': message_id, 'text': text,
                          'parse_mode': 'HTML', 'disable_web_page_preview': True}
                if markup:
                    params['reply_markup'] = markup
                await self.api('editMessageText', **params)
                return
            except BotAPIError as e:
                if 'not modified' in str(e):
                    return
        await self.send(text, markup)

    async def user_client(self):
        """Conecta (una sola vez) tu cuenta personal de Telegram."""
        if self.client is None:
            client = TelegramClient(self.cfg['session'], self.cfg['api_id'], self.cfg['api_hash'])
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError('La cuenta no ha iniciado sesión. Ejecuta primero: python3 login.py')
            self.client = client
        return self.client

    async def close(self):
        if self.client is not None:
            await self.client.disconnect()
            self.client = None

    def save(self):
        save_data(self.data)

    # ---------- pantallas ----------

    def view_menu(self):
        msgs = self.data['messages']
        active = sum(1 for m in msgs.values() if m['enabled'])
        text = ('<b>📬 Programador de mensajes</b>\n\n'
                'Mensajes: <b>%d</b> (activos: <b>%d</b>)\n'
                'Grupos conocidos: <b>%d</b>\n\n'
                'Elige una opción:') % (len(msgs), active, len(self.data['groups']))
        return text, kb([
            [('📋 Mis mensajes', 'list'), ('➕ Nuevo mensaje', 'new')],
            [('🔄 Actualizar lista de grupos', 'refresh')],
        ])

    def view_list(self):
        msgs = self.data['messages']
        if not msgs:
            return ('Todavía no tienes mensajes programados.',
                    kb([[('➕ Nuevo mensaje', 'new')], [('⬅️ Menú', 'menu')]]))
        rows = []
        for mid in sorted(msgs, key=int):
            m = msgs[mid]
            icon = '🟢' if m['enabled'] else '⏸'
            rows.append([('%s %s · cada %s · %d grupos' % (icon, m['name'], fmt_interval(m['interval']),
                                                          len(m['groups'])), 'm:%s' % mid)])
        rows.append([('➕ Nuevo mensaje', 'new'), ('⬅️ Menú', 'menu')])
        return '<b>📋 Tus mensajes</b>\n\nToca uno para editarlo:', kb(rows)

    def view_message(self, mid):
        m = self.data['messages'].get(mid)
        if not m:
            return self.view_list()
        status = '🟢 Activo' if m['enabled'] else '⏸ Pausado'
        if m['enabled']:
            nxt = m['last_sent'] + m['interval'] * 60 - time.time()
            status += ' · próximo envío ' + fmt_remaining(nxt)
        preview = m['text'] or ('(sin texto)' if not m.get('photo') else '')
        if len(preview) > 700:
            preview = preview[:700] + '…'
        group_names = [self.data['groups'].get(g, g) for g in m['groups']]
        groups_txt = ', '.join(esc(n) for n in group_names[:10]) or '<i>ninguno</i>'
        if len(group_names) > 10:
            groups_txt += ' y %d más' % (len(group_names) - 10)
        text = ('<b>✉️ %s</b>\n\n'
                '<b>Estado:</b> %s\n'
                '<b>Intervalo:</b> cada %s\n'
                '<b>Grupos (%d):</b> %s\n'
                '%s'
                '%s\n'
                '<b>Texto:</b>\n<blockquote>%s</blockquote>') % (
            esc(m['name']), status, fmt_interval(m['interval']), len(m['groups']), groups_txt,
            '<b>Imagen:</b> sí 🖼\n' if m.get('photo') else '',
            ('<b>Último resultado:</b> %s\n' % esc(m['last_result'])) if m.get('last_result') else '',
            esc(preview))
        toggle = ('⏸ Pausar', 'tog:%s' % mid) if m['enabled'] else ('▶️ Activar', 'tog:%s' % mid)
        return text, kb([
            [toggle, ('🚀 Enviar ahora', 'now:%s' % mid)],
            [('📝 Editar texto', 'txt:%s' % mid), ('👁 Vista previa', 'pv:%s' % mid)],
            [('👥 Grupos', 'grp:%s:0' % mid), ('⏱ Intervalo', 'iv:%s' % mid)],
            [('✏️ Renombrar', 'ren:%s' % mid), ('🗑 Eliminar', 'del:%s' % mid)],
            [('⬅️ Mis mensajes', 'list')],
        ])

    def view_groups(self, mid, page):
        m = self.data['messages'][mid]
        groups = sorted(self.data['groups'].items(), key=lambda kv: kv[1].lower())
        if not groups:
            return ('No conozco ningún grupo todavía. Pulsa «Actualizar lista de grupos» '
                    'para leer los grupos de tu cuenta.',
                    kb([[('🔄 Actualizar lista de grupos', 'refresh:%s' % mid)],
                        [('⬅️ Volver', 'm:%s' % mid)]]))
        pages = max(1, (len(groups) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
        page = max(0, min(page, pages - 1))
        chunk = groups[page * GROUPS_PER_PAGE:(page + 1) * GROUPS_PER_PAGE]
        selected = set(m['groups'])
        rows = []
        for gid, title in chunk:
            mark = '✅' if gid in selected else '⬜️'
            rows.append([('%s %s' % (mark, title[:40]), 'tg:%s:%s:%d' % (mid, gid, page))])
        nav = []
        if page > 0:
            nav.append(('◀️', 'grp:%s:%d' % (mid, page - 1)))
        nav.append(('%d/%d' % (page + 1, pages), 'noop'))
        if page < pages - 1:
            nav.append(('▶️', 'grp:%s:%d' % (mid, page + 1)))
        rows.append(nav)
        rows.append([('☑️ Todos', 'ga:%s:%d' % (mid, page)), ('✖️ Ninguno', 'gn:%s:%d' % (mid, page))])
        rows.append([('🔄 Actualizar grupos', 'refresh:%s' % mid), ('✅ Listo', 'm:%s' % mid)])
        text = ('<b>👥 Grupos para «%s»</b>\n\nSeleccionados: <b>%d</b> de %d.\n'
                'Toca un grupo para marcarlo o desmarcarlo.') % (esc(m['name']), len(selected), len(groups))
        return text, kb(rows)

    def view_interval(self, mid):
        m = self.data['messages'][mid]
        opts = [(15, '15 min'), (30, '30 min'), (60, '1 h'), (120, '2 h'),
                (180, '3 h'), (360, '6 h'), (720, '12 h'), (1440, '24 h')]
        rows, row = [], []
        for minutes, label in opts:
            mark = '• ' if minutes == m['interval'] else ''
            row.append((mark + label, 'ivs:%s:%d' % (mid, minutes)))
            if len(row) == 4:
                rows.append(row)
                row = []
        rows.append([('✍️ Otro intervalo', 'ivc:%s' % mid)])
        rows.append([('⬅️ Volver', 'm:%s' % mid)])
        return ('<b>⏱ ¿Cada cuánto se envía «%s»?</b>\n\nActual: cada %s' %
                (esc(m['name']), fmt_interval(m['interval']))), kb(rows)

    # ---------- procesamiento de updates ----------

    async def poll(self, timeout):
        try:
            updates = await self.api('getUpdates', _http_timeout=timeout + 15,
                                     offset=self.data['update_offset'], timeout=timeout,
                                     allowed_updates=['message', 'callback_query'])
        except BotAPIError as e:
            log.warning('getUpdates falló: %s', e)
            if 'webhook' in str(e).lower():
                await self.api('deleteWebhook')
            await asyncio.sleep(3)
            return
        except Exception as e:  # red caída, timeout...
            log.warning('Error de red en getUpdates: %s', e)
            await asyncio.sleep(3)
            return
        for upd in updates:
            self.data['update_offset'] = upd['update_id'] + 1
            self.save()
            try:
                if 'callback_query' in upd:
                    await self.on_callback(upd['callback_query'])
                elif 'message' in upd:
                    await self.on_message(upd['message'])
            except Exception as e:
                log.exception('Error procesando update')
                await self.send('⚠️ Error: %s' % esc(e))

    async def on_message(self, msg):
        if msg.get('from', {}).get('id') != self.admin:
            if msg.get('chat', {}).get('type') == 'private':
                await self.send('Este bot es privado.', chat_id=msg['chat']['id'])
            return
        text = msg.get('text', '')
        state = self.data.get('state')

        if text.startswith('/start') or text.startswith('/menu'):
            self.data['state'] = None
            self.save()
            await self.show(self.view_menu())
            return
        if text.startswith('/cancelar') or text.startswith('/cancel'):
            self.data['state'] = None
            self.save()
            await self.send('Cancelado.')
            await self.show(self.view_menu())
            return
        if text.startswith('/id'):
            await self.send('Tu ID es <code>%d</code>' % msg['from']['id'])
            return

        if not state:
            await self.show(self.view_menu())
            return

        mid = state.get('mid')
        m = self.data['messages'].get(mid)
        if not m:
            self.data['state'] = None
            self.save()
            await self.show(self.view_menu())
            return

        action = state['action']
        if action == 'text':
            if 'photo' in msg:
                photo = msg['photo'][-1]  # la de mayor resolución
                f = await self.api('getFile', file_id=photo['file_id'])
                os.makedirs(MEDIA_DIR, exist_ok=True)
                dest = os.path.join(MEDIA_DIR, 'msg%s_%d.jpg' % (mid, int(time.time())))
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.bot.download, f['file_path'], dest)
                self._remove_photo(m)
                m['photo'] = os.path.basename(dest)
                m['photo_file_id'] = photo['file_id']
                m['text'] = msg.get('caption', '')
                m['entities'] = msg.get('caption_entities', [])
            elif text:
                self._remove_photo(m)
                m['text'] = text
                m['entities'] = msg.get('entities', [])
            else:
                await self.send('Envíame un texto o una foto (con texto opcional). /cancelar para salir.')
                return
            self.data['state'] = None
            self.save()
            extra = ''
            if not m['groups']:
                extra = '\n\n👉 Ahora elige los grupos con el botón «👥 Grupos».'
            await self.send('✅ Texto guardado.' + extra)
            await self.show(self.view_message(mid))
        elif action == 'interval':
            minutes = parse_interval(text)
            if not minutes:
                await self.send('No entendí el intervalo. Ejemplos: <code>45</code> (minutos), '
                                '<code>2h</code>, <code>1h30m</code>, <code>1d</code>.')
                return
            m['interval'] = minutes
            self.data['state'] = None
            self.save()
            await self.show(self.view_message(mid))
        elif action == 'name':
            if not text:
                return
            m['name'] = text.strip()[:40]
            self.data['state'] = None
            self.save()
            await self.show(self.view_message(mid))

    def _remove_photo(self, m):
        if m.get('photo'):
            try:
                os.remove(os.path.join(MEDIA_DIR, m['photo']))
            except OSError:
                pass
        m['photo'] = None
        m['photo_file_id'] = None

    async def on_callback(self, cq):
        if cq.get('from', {}).get('id') != self.admin:
            await self.api('answerCallbackQuery', callback_query_id=cq['id'], text='Bot privado')
            return
        data = cq.get('data', '')
        msg_id = cq.get('message', {}).get('message_id')
        parts = data.split(':')
        cmd = parts[0]
        notice = None
        msgs = self.data['messages']

        # Validar que el mensaje referenciado existe
        if cmd not in ('menu', 'list', 'new', 'refresh', 'noop') and len(parts) > 1 and parts[1] not in msgs:
            await self.api('answerCallbackQuery', callback_query_id=cq['id'], text='Ese mensaje ya no existe')
            await self.show(self.view_list(), msg_id)
            return

        if cmd == 'menu':
            self.data['state'] = None
            await self.show(self.view_menu(), msg_id)
        elif cmd == 'list':
            self.data['state'] = None
            await self.show(self.view_list(), msg_id)
        elif cmd == 'noop':
            pass
        elif cmd == 'new':
            mid = str(self.data['next_id'])
            self.data['next_id'] += 1
            msgs[mid] = {'id': mid, 'name': 'Mensaje %s' % mid, 'text': '', 'entities': [],
                         'photo': None, 'photo_file_id': None, 'groups': [], 'interval': 60,
                         'enabled': False, 'last_sent': 0, 'last_result': ''}
            self.data['state'] = {'action': 'text', 'mid': mid}
            await self.show(('<b>➕ Nuevo mensaje</b>\n\nEnvíame ahora el <b>texto</b> que quieres '
                             'publicar (puedes usar negrita, cursiva, enlaces, emojis…).\n'
                             'También puedes enviar una <b>foto con texto</b>.\n\n/cancelar para salir.',
                             None), msg_id)
        elif cmd == 'm':
            self.data['state'] = None
            await self.show(self.view_message(parts[1]), msg_id)
        elif cmd == 'txt':
            self.data['state'] = {'action': 'text', 'mid': parts[1]}
            await self.send('📝 Envíame el <b>nuevo texto</b> (o una foto con texto) para «%s».\n'
                            '/cancelar para salir.' % esc(msgs[parts[1]]['name']))
        elif cmd == 'ren':
            self.data['state'] = {'action': 'name', 'mid': parts[1]}
            await self.send('✏️ Envíame el nuevo nombre (solo lo ves tú). /cancelar para salir.')
        elif cmd == 'pv':
            await self.preview(parts[1])
        elif cmd == 'grp':
            await self.show(self.view_groups(parts[1], int(parts[2])), msg_id)
        elif cmd == 'tg':
            mid, gid, page = parts[1], parts[2], int(parts[3])
            sel = msgs[mid]['groups']
            if gid in sel:
                sel.remove(gid)
            else:
                sel.append(gid)
            await self.show(self.view_groups(mid, page), msg_id)
        elif cmd == 'ga':
            msgs[parts[1]]['groups'] = list(self.data['groups'].keys())
            await self.show(self.view_groups(parts[1], int(parts[2])), msg_id)
        elif cmd == 'gn':
            msgs[parts[1]]['groups'] = []
            await self.show(self.view_groups(parts[1], int(parts[2])), msg_id)
        elif cmd == 'iv':
            await self.show(self.view_interval(parts[1]), msg_id)
        elif cmd == 'ivs':
            msgs[parts[1]]['interval'] = int(parts[2])
            notice = 'Intervalo: cada %s' % fmt_interval(int(parts[2]))
            await self.show(self.view_message(parts[1]), msg_id)
        elif cmd == 'ivc':
            self.data['state'] = {'action': 'interval', 'mid': parts[1]}
            await self.send('✍️ Escribe el intervalo. Ejemplos: <code>45</code> (minutos), '
                            '<code>2h</code>, <code>1h30m</code>, <code>1d</code>.\n/cancelar para salir.')
        elif cmd == 'tog':
            m = msgs[parts[1]]
            if not m['enabled']:
                if not m['text'] and not m.get('photo'):
                    notice = 'Primero escribe el texto'
                elif not m['groups']:
                    notice = 'Primero elige al menos un grupo'
                else:
                    m['enabled'] = True
                    m['last_sent'] = 0  # se envía en el próximo ciclo
                    notice = 'Activado: se enviará en breve y luego cada %s' % fmt_interval(m['interval'])
            else:
                m['enabled'] = False
                notice = 'Pausado'
            await self.show(self.view_message(parts[1]), msg_id)
        elif cmd == 'now':
            m = msgs[parts[1]]
            if not m['groups'] or (not m['text'] and not m.get('photo')):
                notice = 'Falta texto o grupos'
            else:
                await self.api('answerCallbackQuery', callback_query_id=cq['id'], text='Enviando…')
                self.save()
                await self.deliver(parts[1], manual=True)
                await self.show(self.view_message(parts[1]))
                return
        elif cmd == 'del':
            await self.show(('¿Seguro que quieres eliminar «%s»?' % esc(msgs[parts[1]]['name']),
                             kb([[('🗑 Sí, eliminar', 'delok:%s' % parts[1]),
                                  ('Cancelar', 'm:%s' % parts[1])]])), msg_id)
        elif cmd == 'delok':
            self._remove_photo(msgs[parts[1]])
            del msgs[parts[1]]
            notice = 'Eliminado'
            await self.show(self.view_list(), msg_id)
        elif cmd == 'refresh':
            await self.api('answerCallbackQuery', callback_query_id=cq['id'], text='Leyendo tus grupos…')
            n = await self.refresh_groups()
            self.save()
            if len(parts) > 1 and parts[1] in msgs:
                await self.show(self.view_groups(parts[1], 0), msg_id)
            else:
                await self.send('🔄 Encontré <b>%d</b> grupos en tu cuenta.' % n)
                await self.show(self.view_menu())
            return

        self.save()
        try:
            params = {'callback_query_id': cq['id']}
            if notice:
                params['text'] = notice
            await self.api('answerCallbackQuery', **params)
        except BotAPIError:
            pass

    async def preview(self, mid):
        m = self.data['messages'][mid]
        try:
            if m.get('photo_file_id'):
                await self.api('sendPhoto', chat_id=self.admin, photo=m['photo_file_id'],
                               caption=m['text'], caption_entities=m['entities'])
            elif m['text']:
                await self.api('sendMessage', chat_id=self.admin, text=m['text'], entities=m['entities'])
            else:
                await self.send('(Este mensaje no tiene texto todavía)')
        except BotAPIError as e:
            await self.send('No pude mostrar la vista previa: %s' % esc(e))

    # ---------- envío con tu cuenta ----------

    async def refresh_groups(self):
        client = await self.user_client()
        groups = {}
        async for d in client.iter_dialogs():
            ent = d.entity
            if d.is_group:
                groups[str(d.id)] = d.name or str(d.id)
            elif d.is_channel and (getattr(ent, 'creator', False) or
                                   (getattr(ent, 'admin_rights', None) and ent.admin_rights.post_messages)):
                groups[str(d.id)] = '📢 ' + (d.name or str(d.id))
        self.data['groups'] = groups
        self.data['groups_updated'] = time.time()
        return len(groups)

    async def send_one(self, client, gid, m):
        try:
            entity = await client.get_input_entity(int(gid))
        except ValueError:
            await client.get_dialogs()  # recarga la caché de chats
            entity = await client.get_input_entity(int(gid))
        ents = to_telethon_entities(m['entities'])
        if m.get('photo'):
            path = os.path.join(MEDIA_DIR, m['photo'])
            await client.send_file(entity, path, caption=m['text'], formatting_entities=ents)
        else:
            await client.send_message(entity, m['text'], formatting_entities=ents)

    async def deliver(self, mid, manual=False):
        m = self.data['messages'][mid]
        client = await self.user_client()
        ok, failed = 0, []
        for i, gid in enumerate(list(m['groups'])):
            name = self.data['groups'].get(gid, gid)
            if i > 0:
                await asyncio.sleep(random.uniform(self.cfg['pause_min'], self.cfg['pause_max']))
            for attempt in (1, 2):
                try:
                    await self.send_one(client, gid, m)
                    ok += 1
                    break
                except errors.FloodWaitError as e:
                    if attempt == 1 and e.seconds <= 120:
                        log.warning('FloodWait de %ss, esperando…', e.seconds)
                        await asyncio.sleep(e.seconds + 1)
                        continue
                    failed.append('%s (Telegram pide esperar %ss)' % (name, e.seconds))
                    break
                except Exception as e:
                    log.warning('Fallo enviando a %s: %s', name, e)
                    failed.append('%s (%s)' % (name, e.__class__.__name__))
                    break
        result = '%s: %d/%d enviados' % (time.strftime('%d/%m %H:%M'), ok, len(m['groups']))
        m['last_result'] = result
        self.save()
        log.info('Mensaje %s → %s', mid, result)
        if failed or manual or self.cfg['notify']:
            text = '%s <b>%s</b>: enviado a %d de %d grupos.' % (
                '✅' if not failed else '⚠️', esc(m['name']), ok, len(m['groups']))
            if failed:
                text += '\n\nFallaron:\n' + '\n'.join('• ' + esc(f) for f in failed[:20])
            await self.send(text)

    async def send_due(self):
        now = time.time()
        for mid, m in list(self.data['messages'].items()):
            if not m['enabled'] or not m['groups'] or (not m['text'] and not m.get('photo')):
                continue
            period = m['interval'] * 60
            if now - m['last_sent'] < period:
                continue
            # Mantener el ritmo sin acumular retrasos (y sin ráfagas tras una caída)
            if m['last_sent'] and now - m['last_sent'] < 2 * period:
                m['last_sent'] += period
            else:
                m['last_sent'] = now
            self.save()
            try:
                await self.deliver(mid)
            except Exception as e:
                log.exception('Error enviando mensaje %s', mid)
                m['last_result'] = 'Error: %s' % e
                self.save()
                await self.send('⚠️ No pude enviar «%s»: %s' % (esc(m['name']), esc(e)))


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

async def run(cfg, max_seconds=None):
    app = App(cfg)
    deadline = time.time() + max_seconds if max_seconds else None
    try:
        while True:
            await app.send_due()
            if deadline is not None:
                remaining = deadline - time.time()
                if remaining < 3:
                    break
                timeout = int(min(25, remaining - 2))
            else:
                timeout = 25
            await app.poll(timeout)
    finally:
        await app.close()


def acquire_lock():
    if fcntl is None:
        return True
    global _lock_file
    _lock_file = open(LOCK_PATH, 'w')
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (IOError, OSError):
        return False


def main():
    cron = '--cron' in sys.argv
    handlers = [logging.FileHandler(LOG_PATH, encoding='utf-8')]
    if not cron:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('telethon').setLevel(logging.WARNING)

    if not acquire_lock():
        if not cron:
            print('Ya hay otra instancia del bot ejecutándose.')
        return

    cfg = load_config()
    coro = run(cfg, max_seconds=55 if cron else None)
    if hasattr(asyncio, 'run'):
        asyncio.run(coro)
    else:  # Python 3.6
        asyncio.get_event_loop().run_until_complete(coro)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
