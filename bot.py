
import os
import re
import asyncio
import logging

import requests
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
DISCOGS_TOKEN = os.environ["DISCOGS_TOKEN"]

DISCOGS_API = "https://api.discogs.com"
HEADERS = {
    "User-Agent": "DiscogsStyleTelegramBot/1.0",
    "Authorization": f"Discogs token={DISCOGS_TOKEN}",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DISCOGS_LINK_RE = re.compile(
    r"https?://(?:www\.)?discogs\.com/"
    r"(release|master)/(\d+)(?:-[^\s]*)?",
    re.IGNORECASE,
)


def get_discogs_styles(url: str) -> list[str]:
    """Получает Styles для релиза или мастер-релиза."""
    match = DISCOGS_LINK_RE.search(url)

    if not match:
        return []

    resource_type, resource_id = match.groups()
    endpoint = "releases" if resource_type.lower() == "release" else "masters"

    response = requests.get(
        f"{DISCOGS_API}/{endpoint}/{resource_id}",
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    return data.get("styles", []) or []


def make_hashtags(styles: list[str]) -> str:
    """Превращает Future Garage в #FutureGarage."""
    hashtags = []

    for style in styles:
        tag = re.sub(r"[^\w]", "", style, flags=re.UNICODE)

        if tag:
            hashtags.append(f"#{tag}")

    return " ".join(dict.fromkeys(hashtags))


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text or not message.from_user:
        return

    # Не обрабатываем сообщения других ботов.
    if message.from_user.is_bot:
        return

    match = DISCOGS_LINK_RE.search(message.text)

    if not match:
        return

    # Сначала получаем стили. Если Discogs не отвечает,
    # исходное сообщение останется в группе.
    try:
        styles = await asyncio.to_thread(
            get_discogs_styles,
            match.group(0),
        )
    except Exception:
        logger.exception("Не удалось получить данные Discogs")
        return

    original_text = message.text.strip()
    hashtags = make_hashtags(styles)

    username = message.from_user.username
    author = f"@{username}" if username else message.from_user.full_name

    parts = [original_text]

    if hashtags:
        parts.append(hashtags)

    parts.append(author)
    new_text = "\n\n".join(parts)

    # Telegram ограничивает длину текстового сообщения.
    if len(new_text) > 4096:
        logger.warning("Сообщение слишком длинное, оригинал сохранён")
        return

    # Удаляем исходник и публикуем обработанную версию.
    try:
        await message.delete()
    except Exception:
        logger.exception("Не удалось удалить исходное сообщение")
        return

    try:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=new_text,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Не удалось опубликовать новое сообщение")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Discogs Style Bot запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
