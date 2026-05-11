import json
import logging
import threading
import urllib.request

logger = logging.getLogger(__name__)


def send_tg_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a Telegram message in a daemon thread. Never raises."""
    def _send():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.warning("TG notify failed chat_id=%s: %s", chat_id, exc)
    threading.Thread(target=_send, daemon=True).start()
