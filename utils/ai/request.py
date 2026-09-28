import base64
from openai import AsyncOpenAI
from config_data.config import Config, load_config

config: Config = load_config()

client = AsyncOpenAI(
    api_key=config.ai.api_key,
    base_url=config.ai.api_base if config.ai.api_base else None,
)

async def get_ai_answer(user_prompt: str, system_prompt: str | None = None, image_base64: str = None):
    if not image_base64:
        messages = [{"role": "user", "content": user_prompt}]
    else:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

    # Prepare system message if provided
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    formatted_messages.extend(messages)

    response = await client.chat.completions.create(
        model=config.ai.model,
        messages=formatted_messages,
        max_tokens=2048,
        temperature=0.7,
    )
    return response.choices[0].message.content