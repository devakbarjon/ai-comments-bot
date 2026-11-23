import asyncio
import logging
import random
import re
from pathlib import Path

from aiogram.types import CallbackQuery, User, Message
from aiogram_dialog import DialogManager, ShowMode
from aiogram_dialog.api.entities import MediaAttachment
from aiogram_dialog.widgets.kbd import Button, Select
from aiogram_dialog.widgets.input import ManagedTextInput, MessageInput
from pyrogram import Client
from pyrogram.types import SentCode
from pyrogram.errors import (
    AuthKeyUnregistered,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    SessionPasswordNeeded,
)

from utils.ai.adder import get_channel_analysis
from services.session_manager import SessionManager
from utils.collect_funcs import get_channel, subscribe_accounts
from database.model import ChannelsTable, AccountsTable
from database.action_data_class import DataInteraction
from config_data.config import load_config, Config
from states.state_groups import startSG


config: Config = load_config()
logger = logging.getLogger(__name__)


def _account_key(name: str) -> str:
    return re.sub(r'[^\w-]+', '_', name.strip()).strip('_-')


async def _disconnect_login_client(client: Client | None) -> None:
    if client and client.is_connected:
        try:
            await client.disconnect()
        except Exception:
            logger.exception('Failed to disconnect Telegram login client')


async def _reset_invalid_login(dialog_manager: DialogManager, client: Client | None) -> None:
    base_id = dialog_manager.dialog_data.get('base_id')
    account_key = dialog_manager.dialog_data.get('account_key')
    await _disconnect_login_client(client)

    if account_key:
        session_path = Path('accounts') / f'{account_key}.session'
        for path in (session_path, Path(f'{session_path}-journal')):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception('Failed to remove invalid Telegram session file %s', path)

    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data['base_id'] = base_id
    await dialog_manager.switch_to(startSG.get_name)


async def _complete_account_add(
    message: Message,
    dialog_manager: DialogManager,
    client: Client,
) -> None:
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    manager: SessionManager = dialog_manager.middleware_data.get('manager')
    base_id = dialog_manager.dialog_data.get('base_id')
    name = dialog_manager.dialog_data.get('name')
    account_key = dialog_manager.dialog_data.get('account_key')
    account_type = dialog_manager.dialog_data.get('account_type')

    await client.get_me()
    await _disconnect_login_client(client)

    if not await manager.add(account_key):
        raise RuntimeError('The Telegram session could not be activated.')
    try:
        await session.add_base_account(base_id, account_key, name, account_type)
    except Exception:
        await manager.remove(account_key)
        raise

    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data['base_id'] = base_id
    await message.answer(text='✅ Ваш аккаунт был успешно добавлен')
    await dialog_manager.switch_to(state=startSG.accounts)
    for channel in await session.get_channels(base_id):
        asyncio.create_task(subscribe_accounts(base_id, channel.id, manager, session))


async def start_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    admin = False
    if event_from_user.id in config.bot.admin_ids:
        admin = True
    return {
        'admin': admin
    }


async def get_base_name(msg: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    if len(text) > 15:
        await msg.answer('Название базы должно быть не длиннее 15 символов')
        return
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    await session.add_base(name=text)
    await msg.answer('База была успешно добавлена')
    dialog_manager.dialog_data.clear()
    await dialog_manager.switch_to(startSG.bases)


async def bases_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    bases = await session.get_bases()
    buttons = []
    for base in bases:
        buttons.append((base.name, base.id))
    return {
        'items': buttons
    }


async def base_select(clb: CallbackQuery, widget: Select, dialog_manager: DialogManager, item_id: str):
    dialog_manager.dialog_data['base_id'] = int(item_id)
    await dialog_manager.switch_to(startSG.base)


async def base_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    channels: list[ChannelsTable] = base.channels if base.channels else []
    accounts: list[AccountsTable] = base.accounts if base.accounts else []
    channel_text = '<b>Каналы:</b>'
    for channel in channels:
        channel_text += f'\n - ({channel.id}) {channel.name}'
    account_text = '<b>Аккаунты (боты):</b>'
    for account in accounts:
        account_text += f'\n - ({account.id}) {account.name}'
    return {
        'base_id': base_id,
        'name': base.name,
        'channels': channel_text if channels else "Каналы отсутствуют",
        'accounts': account_text if accounts else "Аккаунты (боты) отсутствуют"
    }


async def del_base(clb: CallbackQuery, widget: Button, dialog_manager: DialogManager):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    manager: SessionManager = dialog_manager.middleware_data.get('manager')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    accounts: list[AccountsTable] = base.accounts if base.accounts else []
    for account in accounts:
        if not await manager.remove(account.account):
            await clb.answer('Не удалось удалить сессию аккаунта. Попробуйте позже.', show_alert=True)
            return
    await session.del_base(base_id)
    await clb.answer('База была успешно удаленна')
    dialog_manager.dialog_data.clear()
    await dialog_manager.switch_to(startSG.start)


async def channels_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    channels: list[ChannelsTable] = base.channels if base.channels else []
    channel_text = '<b>Каналы:</b>'
    for channel in channels:
        channel_text += f'\n - ({channel.id}) {channel.name}'
    return {
        'base_name': base.name,
        'channels': channel_text if channels else "Каналы отсутствуют",
    }


async def check_account(clb: CallbackQuery, widget: Button, dialog_manager: DialogManager):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    if not base.accounts:
        await clb.answer('Перед началом добавления каналов пожалуйста добавьте хотя бы один аккаунт (бот)')
        return
    await dialog_manager.switch_to(startSG.get_base_channel)


async def get_base_channel(msg: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    try:
        text = int(text)
    except Exception as err:
        print(err)
        if text.startswith('@'):
            text = text[1::]
        elif 't.me' not in text:
            await msg.answer('❗️Вы ввели ссылку не в том формате, пожалуйста попробуйте снова')
            return
        try:
            text = text.split('/')[-1]
        except Exception:
            await msg.answer('❗️Вы ввели ссылку не в том формате, пожалуйста попробуйте снова')
            return
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    manager: SessionManager = dialog_manager.middleware_data.get('manager')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    account = random.choice(list(base.accounts))
    client: Client = manager.get(account.account)
    channel = await get_channel(
        client,
        text
    )
    if not channel:
        await msg.answer('❗️Такого канала не найдено, пожалуйста попробуйте снова')
        return
    status, _, chat = await subscribe_accounts(base_id, channel.id, manager, session)
    if not status or chat is None:
        await msg.answer('❗️Во время получения данных о чате комментариев в каналу произошла какая ошибка, '
                         'пожалуйста попробуйте снова')
        return
    try:
        analysis = await get_channel_analysis(client, channel)
    except Exception as err:
        await msg.answer(f'❗️Во время анализа канала произошла какая-то ошибка, пожалуйста попробуйте снова'
                         f'\n\nОшибка: <code>{err}</code>')
        return
    await session.add_channel(base_id, channel.id, chat.id, channel.title, analysis.topic, analysis.tone, analysis.audience)
    await msg.answer('Канал был успешно добавлен')
    await dialog_manager.switch_to(startSG.channels)


async def get_forward_message(msg: Message, widget: MessageInput, dialog_manager: DialogManager):
    if msg.forward_from_chat is None:
        await msg.answer('❗️К сожалению невозможно получить данные о канале из-за правил конфиденциальности канала')
        return
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    manager: SessionManager = dialog_manager.middleware_data.get('manager')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    account = random.choice(list(base.accounts))
    client: Client = manager.get(account.account)
    channel = await get_channel(
        client,
        msg.forward_from_chat.id
    )
    if not channel:
        await msg.answer('❗️Такого канала не найдено, пожалуйста попробуйте снова')
        return
    status, _, chat = await subscribe_accounts(base_id, channel.id, manager, session)
    if not status or chat is None:
        await msg.answer('❗️Во время получения данных о чате комментариев в каналу произошла какая ошибка, '
                         'пожалуйста попробуйте снова')
        return
    try:
        analysis = await get_channel_analysis(client, channel)
    except Exception as err:
        print(err)
        await msg.answer(f'❗️Во время анализа канала произошла какая-то ошибка, пожалуйста попробуйте снова'
                         f'\n\nОшибка: <code>{err}</code>')
        return
    await session.add_channel(base_id, channel.id, chat.id, channel.title, analysis.topic, analysis.tone, analysis.audience)
    await msg.answer('Канал был успешно добавлен')
    await dialog_manager.switch_to(startSG.channels)


async def del_channel_getter(dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    channels = await session.get_channels(base_id)
    buttons = []
    for channel in channels:
        buttons.append((channel.name, channel.id))

    return {
        'items': buttons
    }


async def del_channel_selector(clb: CallbackQuery, widget: Select, dialog_manager: DialogManager, item_id: str):
    dialog_manager.dialog_data['channel_id'] = int(item_id)
    await dialog_manager.switch_to(startSG.del_channel_confirm)


async def del_channel_confirm_getter(dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    channel_id = dialog_manager.dialog_data.get('channel_id')
    channel = await session.get_channel_by_id(channel_id)
    return {
        'title': channel.name
    }


async def del_channel(clb: CallbackQuery, widget: Button, dialog_manager: DialogManager):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    channel_id = dialog_manager.dialog_data.get('channel_id')
    await session.del_channel(channel_id)
    await clb.answer('Канал был успешно удален')
    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data['base_id'] = base_id
    await dialog_manager.switch_to(startSG.channels)


async def accounts_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    base = await session.get_base(base_id)
    accounts = base.accounts if base.accounts else []
    text = ''
    if accounts:
        text = 'Добавленные аккаунты:\n'
        count = 1
        for account in accounts:
            text += f'\t{count} - {account.name}'
            count += 1
    return {
        'base_name': base.name,
        'text': text
    }


async def del_account_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    base_id = dialog_manager.dialog_data.get('base_id')
    accounts = await session.get_accounts(base_id)
    buttons = []
    for account in accounts:
        buttons.append(
            (account.name, account.id)
        )
    return {'items': buttons}


async def del_account_selector(clb: CallbackQuery, widget: Select, dialog_manager: DialogManager, item_id: str):
    dialog_manager.dialog_data['account_id'] = int(item_id)
    await dialog_manager.switch_to(startSG.del_account_confirm)


async def del_account_confirm_getter(event_from_user: User, dialog_manager: DialogManager, **kwargs):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    account_id = dialog_manager.dialog_data.get('account_id')
    account = await session.get_account(account_id)
    return {'name': account.name}


async def del_account(clb: CallbackQuery, button: Button, dialog_manager: DialogManager):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    manager: SessionManager = dialog_manager.middleware_data.get('manager')
    base_id = dialog_manager.dialog_data.get('base_id')
    account_id = dialog_manager.dialog_data.get('account_id')
    account = await session.get_account(account_id)
    if not await manager.remove(account.account):
        await clb.answer('Не удалось удалить сессию аккаунта. Попробуйте позже.', show_alert=True)
        return
    await session.del_account(account_id)
    await clb.answer('Аккаунт был успешно удален')
    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data['base_id'] = base_id
    await dialog_manager.switch_to(startSG.accounts)


async def get_name(msg: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    session: DataInteraction = dialog_manager.middleware_data.get('session')
    name = text.strip()
    account_key = _account_key(name)
    if not account_key:
        await msg.answer('❗️Введите название, содержащее буквы или цифры')
        return
    if len(account_key) > 64:
        await msg.answer('❗️Название аккаунта слишком длинное')
        return
    if account_key in {account.account for account in await session.get_all_accounts()}:
        await msg.answer('❗️У вас уже есть аккаунт с таким названием, пожалуйста придумайте другое название')
        return
    dialog_manager.dialog_data['name'] = name
    dialog_manager.dialog_data['account_key'] = account_key
    await dialog_manager.switch_to(startSG.choose_account_type)


async def choose_account_type(clb: CallbackQuery, widget: Button, dialog_manager: DialogManager):
    dialog_manager.dialog_data['account_type'] = clb.data.split('_')[0]
    await dialog_manager.switch_to(startSG.add_account)


async def phone_get(msg: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    name = dialog_manager.dialog_data.get('name')
    account_key = dialog_manager.dialog_data.get('account_key')
    if not name or not account_key:
        await msg.answer('❗️Состояние добавления аккаунта потеряно. Начните заново.')
        await dialog_manager.switch_to(startSG.get_name)
        return

    Path('accounts').mkdir(parents=True, exist_ok=True)
    client = Client(
        str(Path('accounts') / account_key),
        config.user_bot.api_id,
        config.user_bot.api_hash,
    )
    try:
        await client.connect()
        sent_code_info: SentCode = await client.send_code(text.strip())
    except AuthKeyUnregistered:
        logger.exception('The stored login session for account %s is invalid', account_key)
        await _reset_invalid_login(dialog_manager, client)
        await msg.answer('❗️Сессия входа устарела. Начните добавление аккаунта заново.')
        return
    except Exception:
        logger.exception('Failed to request a Telegram login code')
        await _disconnect_login_client(client)
        await msg.answer('❗️Не удалось отправить код входа. Проверьте номер и попробуйте снова.')
        return
    dialog_manager.dialog_data['client'] = client
    dialog_manager.dialog_data['phone_info'] = sent_code_info
    dialog_manager.dialog_data['phone_number'] = text.strip()
    await dialog_manager.switch_to(state=startSG.kod_send)


async def get_kod(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    client: Client = dialog_manager.dialog_data.get('client')
    phone_info: SentCode = dialog_manager.dialog_data.get('phone_info')
    phone = dialog_manager.dialog_data.get('phone_number')
    if not client or not phone_info or not phone:
        await message.answer('❗️Состояние входа потеряно. Начните добавление аккаунта заново.')
        await _reset_invalid_login(dialog_manager, client)
        return

    code = text.replace('-', '').strip()
    if not code.isdigit() or not 4 <= len(code) <= 8:
        await message.answer('❗️Неверный формат кода. Отправьте код из Telegram.')
        return

    try:
        await client.sign_in(phone, phone_info.phone_code_hash, code)
        await _complete_account_add(message, dialog_manager, client)
    except SessionPasswordNeeded:
        await dialog_manager.switch_to(state=startSG.get_password)
    except PhoneCodeInvalid:
        await message.answer('❗️Код неверный. Проверьте его и попробуйте снова.')
    except PhoneCodeExpired:
        await _reset_invalid_login(dialog_manager, client)
        await message.answer('❗️Код истёк. Начните добавление аккаунта заново.')
    except AuthKeyUnregistered:
        logger.exception('Telegram invalidated the login session during code verification')
        await _reset_invalid_login(dialog_manager, client)
        await message.answer('❗️Сессия входа устарела. Начните добавление аккаунта заново.')
    except Exception:
        logger.exception('Failed to verify Telegram login code')
        await message.answer('❗️Не удалось завершить вход. Попробуйте ещё раз.')


async def get_password(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    client: Client = dialog_manager.dialog_data.get('client')
    if not client:
        await message.answer('❗️Состояние входа потеряно. Начните добавление аккаунта заново.')
        await _reset_invalid_login(dialog_manager, client)
        return

    try:
        await client.check_password(text)
        await _complete_account_add(message, dialog_manager, client)
    except PasswordHashInvalid:
        await message.answer(text='❗️Введенные данные были неверны, пожалуйста попробуйте авторизоваться снова')
    except AuthKeyUnregistered:
        logger.exception('Telegram invalidated the login session during password verification')
        await _reset_invalid_login(dialog_manager, client)
        await message.answer('❗️Сессия входа устарела. Начните добавление аккаунта заново.')
    except Exception:
        logger.exception('Failed to verify Telegram two-step verification password')
        await message.answer('❗️Не удалось завершить вход. Попробуйте ещё раз.')
