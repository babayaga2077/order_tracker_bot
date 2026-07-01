import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    chat_id: int
    track17_api_key: str
    db_path: str
    generic_store_state_path: Optional[str]


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )
    chat_id_raw = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id_raw:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID is not set. See README for how to find your chat_id once."
        )
    return Config(
        bot_token=token,
        chat_id=int(chat_id_raw),
        track17_api_key=os.getenv("TRACK17_API_KEY", ""),
        db_path=os.getenv("DB_PATH", "orders.db"),
        generic_store_state_path=os.getenv("GENERIC_STORE_STATE_PATH") or None,
    )
