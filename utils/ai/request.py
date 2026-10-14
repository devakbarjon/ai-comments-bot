import logging

from openai import AsyncOpenAI
from config_data.config import Config, load_config

logger = logging.getLogger(__name__)

config: Config = load_config()

providers: list[tuple[str, AsyncOpenAI, str]] = [
    (
        'OpenRouter',
        AsyncOpenAI(
            api_key=config.ai.api_key,
            base_url=config.ai.api_base if config.ai.api_base else None,
            max_retries=0,
        ),
        config.ai.model,
    )
]


def _has_configured_key(api_key: str) -> bool:
    return bool(api_key.strip()) and not api_key.strip().lower().startswith(
        ('your_', 'placeholder')
    )


if _has_configured_key(config.ai.gemini_api_key):
    providers.append((
        'Gemini',
        AsyncOpenAI(
            api_key=config.ai.gemini_api_key,
            base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
            max_retries=0,
        ),
        config.ai.gemini_model,
    ))

if _has_configured_key(config.ai.groq_api_key):
    providers.append((
        'Groq',
        AsyncOpenAI(
            api_key=config.ai.groq_api_key,
            base_url='https://api.groq.com/openai/v1',
            max_retries=0,
        ),
        config.ai.groq_model,
    ))


async def get_ai_answer(user_prompt: str, system_prompt: str | None = None):
    # Prepare system message if provided
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    formatted_messages.append({"role": "user", "content": user_prompt})

    failures: list[str] = []
    last_error: Exception | None = None
    for provider_name, provider_client, model in providers:
        try:
            response = await provider_client.chat.completions.create(
                model=model,
                messages=formatted_messages,
                max_tokens=2048,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError(f'{provider_name} returned an empty response')
            return content
        except Exception as err:
            last_error = err
            failures.append(f'{provider_name}: {err}')
            logger.warning(
                '%s generation failed; moving to the next configured provider: %s',
                provider_name,
                err,
            )

    failure_details = '; '.join(failures)
    logger.error('All configured AI providers failed: %s', failure_details)
    raise RuntimeError(
        f'All configured AI providers failed: {failure_details}'
    ) from last_error