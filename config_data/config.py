from dataclasses import dataclass

from environs import Env

'''
    При необходимости конфиг базы данных или других сторонних сервисов
'''


@dataclass
class tg_bot:
    token: str
    admin_ids: list[int]


@dataclass
class DB:
    dns: str


@dataclass
class UserBot:
    api_id: int
    api_hash: str


@dataclass
class AIConfig:
    api_key: str
    api_base: str
    model: str
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str


@dataclass
class Config:
    bot: tg_bot
    user_bot: UserBot
    db: DB
    ai: AIConfig


def load_config(path: str | None = None) -> Config:
    env: Env = Env()
    env.read_env(path)

    return Config(
        bot=tg_bot(
            token=env('TOKEN'),
            admin_ids=list(map(int, env.list('ADMINS')))
        ),
        user_bot=UserBot(
            api_id=int(env('API_ID')),
            api_hash=env('API_HASH')
        ),
        db=DB(
            dns=env('DNS')
        ),
        ai=AIConfig(
            api_key=env('AI_API_KEY'),
            api_base=env('AI_API_BASE'),
            model=env('AI_MODEL'),
            gemini_api_key=env.str('GEMINI_API_KEY', default=''),
            gemini_model=env.str('GEMINI_MODEL', default='gemini-2.5-flash'),
            groq_api_key=env.str('GROQ_API_KEY', default=''),
            groq_model=env.str('GROQ_MODEL', default='llama-3.3-70b-versatile')
        )
    )
