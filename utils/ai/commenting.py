from typing import Literal

from pyrogram.types import Message

from utils.ai.request import get_ai_answer
from utils.ai.adder import get_post_analysis
from utils.ai.errors import AIGenerationError, AnalysisError
from database.model import ChannelsTable


prompts = {
    'special': """You are a genuine Uzbek-speaking Telegram channel participant.
        Your goal is to write comments that appear as if written by a real person.
        Key principles:
        - Be relevant: Respond specifically to the post's content, not generic remarks
        - Match the channel's style: Adapt your tone to fit the channel's usual vibe
        - Keep it natural: Avoid AI-like phrases, be spontaneous and varied
        - Respect length: Strictly adhere to the requested comment length (ultrashort/short/medium)
        - Language: Write exclusively in Uzbek, ensuring grammatical correctness
        - Be engaging: When appropriate, aim to be humorous, supportive, or thought-provoking
        - Be original: Never repeat the post text or use templated responses""",

    'general': """You are a genuine Russian-speaking Telegram channel participant.
        Your goal is to write comments that appear as if written by a real person.
        Key principles:
        - Be relevant: Respond specifically to the post's content, not generic remarks
        - Match the channel's style: Adapt your tone to fit the channel's usual vibe
        - Keep it natural: Avoid AI-like phrases, be spontaneous and varied
        - Respect length: Strictly adhere to the requested comment length (ultrashort/short/medium)
        - Language: Write exclusively in Russian, ensuring grammatical correctness
        - Be engaging: When appropriate, aim to be humorous, supportive, or thought-provoking
        - Be original: Never repeat the post text or use templated responses"""
}


async def get_comment(message: Message, channel: ChannelsTable, account_type: Literal['special', 'general'], image_base64: str = None) -> str:
    try:
        analytics = await get_post_analysis(message)
    except Exception as err:
        raise AnalysisError(err)
    system_prompt = prompts.get(account_type)
    user_prompt = f'''
    CHANNEL INFORMATION:
    - Topic: {channel.topic}
    - CHANNEL TONE (with which to contrast or agree): {channel.tone}
    - Target audience: {channel.audience}

    POST INFORMATION (from summarizer):
    - Brief essence: {analytics.summary}
    - Post mood: {analytics.mood}
    - Recommended emotion: {analytics.recommended_emotion}
    - Recommended length: {analytics.comment_length_style}  # ultrashort / short / medium
    - Main topic: {analytics.main_topic}
    - Key entities: {", ".join(analytics.key_entities)}

    FULL POST TEXT:
    {message.content}

    TASK:
    Write a comment in first person. REQUIREMENTS:
    1. Length must strictly correspond to "{analytics.comment_length_style}"
       - ultrashort = 2-5 words (meme, exclamation, short joke)
       - short = 1 sentence (up to 12 words)
       - medium = 2 sentences (maximum)
    2. Use Russian internet jokes and memes if appropriate
    3. Don't reflect - react emotionally or with irony
    4. Don't call to profile, don't say "I have a post"

    PROHIBITIONS:
    - Profanity - only in extreme cases and with censorship (damn, shit - acceptable)
    - Mention of Halal

    RETURN ONLY the comment text.
    '''
    try:
        answer = await get_ai_answer(user_prompt, system_prompt, image_base64)
        print(f'AI comment result:\n{answer}')
    except Exception as err:
        print(f'AI Gen comment err: {err}')
        raise AIGenerationError(err)
    return answer
