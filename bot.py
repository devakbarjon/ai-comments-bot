import asyncio
import logging
import os
import inspect
import pytz
import datetime

from aiogram import Bot, Dispatcher
from aiogram_dialog import setup_dialogs
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.session_manager import SessionManager, test_func
from database.build import PostgresBuild
from database.model import Base
from database.action_data_class import DataInteraction
from config_data.config import load_config, Config
from handlers.user_handlers import user_router
from dialogs import get_dialogs
from middlewares import TransferObjectsMiddleware


timezone = pytz.timezone('Europe/Moscow')
datetime.datetime.now(timezone)

module_path = inspect.getfile(inspect.currentframe())
module_dir = os.path.realpath(os.path.dirname(module_path))


format = '[{asctime}] #{levelname:8} {filename}:' \
         '{lineno} - {name} - {message}'

logging.basicConfig(
    level=logging.INFO,
    format=format,
    style='{'
)


logger = logging.getLogger(__name__)

config: Config = load_config()


async def handle_update_error(event: ErrorEvent) -> bool:
    error = event.exception
    logger.error(
        'Unhandled Telegram update error: %s',
        error,
        exc_info=(type(error), error, error.__traceback__),
    )

    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(
                'An unexpected error occurred. Please try again.',
                show_alert=True,
            )
        elif event.update.message:
            await event.update.message.answer(
                'An unexpected error occurred. Please try again.'
            )
    except TelegramAPIError:
        logger.exception('Could not send an error notification to the user')

    return True


async def _setup_sessions(manager: SessionManager, db: DataInteraction):
    for account in await db.get_all_accounts():
        await manager.add(account.account)
    await manager.start()


async def main():
    database = PostgresBuild(config.db.dns)
    #await database.drop_tables(Base)
    await database.create_tables(Base)
    session = database.session()
    db = DataInteraction(session)

    scheduler: AsyncIOScheduler = AsyncIOScheduler()
    scheduler.start()

    manager = SessionManager(config.user_bot.api_id, config.user_bot.api_hash, db)

    bot = Bot(token=config.bot.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # подключаем роутеры
    dp.include_routers(user_router, *get_dialogs())
    dp.errors.register(handle_update_error)

    await _setup_sessions(manager, db)
    # await asyncio.sleep(9)
    # await test_func(db, manager)
    # await manager.stop()
    # return

    # подключаем middleware
    dp.update.middleware(TransferObjectsMiddleware())

    setup_dialogs(dp)
    # запуск
    try:
        retry_delay = 1
        drop_pending_updates = True
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
                drop_pending_updates = False
                logger.info('Bot start polling')
                await dp.start_polling(
                    bot,
                    _session=session,
                    _scheduler=scheduler,
                    manager=manager,
                    close_bot_session=False,
                )
                break
            except Exception:
                logger.exception(
                    'Bot polling stopped unexpectedly; retrying in %s seconds',
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
    finally:
        try:
            await manager.stop()
        finally:
            scheduler.shutdown(wait=False)
            await bot.session.close()
            logger.info('Connection closed')


if __name__ == "__main__":
    asyncio.run(main())