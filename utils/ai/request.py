from openai import AsyncOpenAI, RateLimitError
from config_data.config import Config, load_config

config: Config = load_config()

client = AsyncOpenAI(
    api_key=config.ai.api_key,
    base_url=config.ai.api_base if config.ai.api_base else None,
)

gemini_client = (
    AsyncOpenAI(
        api_key=config.ai.gemini_api_key,
        base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
    )
    if config.ai.gemini_api_key
    else None
)


async def get_ai_answer(user_prompt: str, system_prompt: str | None = None):
    # Prepare system message if provided
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    formatted_messages.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=config.ai.model,
            messages=formatted_messages,
            max_tokens=2048,
            temperature=0.7,
        )
    except RateLimitError:
        if gemini_client is None:
            raise
        response = await gemini_client.chat.completions.create(
            model=config.ai.gemini_model,
            messages=formatted_messages,
            max_tokens=2048,
            temperature=0.7,
        )
    return response.choices[0].message.content