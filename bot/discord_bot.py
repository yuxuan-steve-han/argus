import asyncio
import json

import discord
import httpx

import config
import monitor

_SYSTEM_PROMPT = (
    "You are a helpful home security assistant. You are part of a home security system "
    "that monitors cameras, detects motion, and analyzes suspicious activity. "
    "Answer the user's questions helpfully and concisely."
)


class SecurityBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_ready(self):
        monitor.log(f"Discord bot logged in as {self.user}", "INFO")

    async def on_message(self, message: discord.Message):
        if message.author == self.user or message.author.bot:
            return

        # Only respond to mentions or DMs
        if not (self.user in message.mentions or isinstance(message.channel, discord.DMChannel)):
            return

        # Strip the mention from the content
        text = message.content
        if self.user:
            text = text.replace(f"<@{self.user.id}>", "").strip()

        if not text:
            await message.reply("Hey! Ask me anything about your home security system.")
            return

        monitor.log(f"Bot query from {message.author}: {text}", "INFO")

        async with message.channel.typing():
            reply = await _chat(text)

        await message.reply(reply)


async def _chat(user_message: str) -> str:
    if config.LLM_BACKEND == "ollama":
        return await _chat_ollama(user_message)
    return await _chat_claude(user_message)


async def _chat_claude(user_message: str) -> str:
    import anthropic

    def _call():
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.DISCORD_BOT_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)
    except Exception as e:
        monitor.log(f"Bot LLM error: {e}", "ERROR")
        return f"Sorry, I hit an error: {e}"


async def _chat_ollama(user_message: str) -> str:
    base_url = config.OLLAMA_URL.rstrip("/")
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT) as client:
            resp = await client.post(f"{base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
    except Exception as e:
        monitor.log(f"Bot Ollama error: {e}", "ERROR")
        return f"Sorry, I hit an error: {e}"


_bot: SecurityBot | None = None


async def start():
    global _bot
    if not config.DISCORD_BOT_TOKEN:
        monitor.log("DISCORD_BOT_TOKEN not set — bot disabled", "INFO")
        return
    _bot = SecurityBot()
    await _bot.start(config.DISCORD_BOT_TOKEN)
