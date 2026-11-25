#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inicia sesión con TU cuenta de Telegram (solo hay que hacerlo una vez).
Te pedirá tu número de teléfono, el código que te llega por Telegram y,
si la tienes, tu contraseña de verificación en dos pasos.

Crea el archivo de sesión (cuenta.session). ¡No lo compartas con nadie!
Quien tenga ese archivo puede usar tu cuenta.
"""
import asyncio

from telethon import TelegramClient

from bot import load_config


async def main():
    cfg = load_config()
    client = TelegramClient(cfg['session'], cfg['api_id'], cfg['api_hash'])
    def ask_phone():
        while True:
            phone = input('Tu número de teléfono de Telegram (con prefijo, ej. +52 81 1234 5678): ').strip()
            if ':' in phone or not phone.lstrip('+').replace(' ', '').isdigit():
                print('❌ Eso no es un número de teléfono (no pongas el token del bot aquí).')
                continue
            return phone

    await client.start(phone=ask_phone)
    me = await client.get_me()
    if me.bot:
        await client.log_out()
        print('❌ Se inició sesión como un BOT, no con tu cuenta. Vuelve a ejecutar: python3 login.py')
        return
    print('\n✅ Sesión iniciada como: %s %s (@%s), ID: %d' % (
        me.first_name or '', me.last_name or '', me.username or '-', me.id))
    if me.id != cfg['admin_id']:
        print('⚠️  Ojo: admin_id en config.ini (%d) no coincide con tu ID (%d). '
              'Corrígelo para poder controlar el bot.' % (cfg['admin_id'], me.id))
    n = 0
    async for d in client.iter_dialogs():
        if d.is_group:
            n += 1
    print('Grupos encontrados en tu cuenta: %d' % n)
    await client.disconnect()


if __name__ == '__main__':
    if hasattr(asyncio, 'run'):
        asyncio.run(main())
    else:
        asyncio.get_event_loop().run_until_complete(main())
