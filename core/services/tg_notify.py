import json
import logging
import threading
import uuid
import urllib.request

logger = logging.getLogger(__name__)


def send_tg_message(bot_token: str, chat_id: str, text: str, *, run_async: bool = True) -> None:
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
    if run_async:
        threading.Thread(target=_send, daemon=True).start()
        return
    _send()


def send_tg_document(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    *,
    run_async: bool = True,
    timeout_seconds: int = 120,
) -> bool:
    """Send a Telegram document. Returns True on success. Never raises when run_async=True."""
    upload_timeout = max(15, int(timeout_seconds or 120))

    def _send() -> bool:
        try:
            with open(file_path, "rb") as fh:
                file_bytes = fh.read()

            boundary = f"----adminantizapret-{uuid.uuid4().hex}"
            body = bytearray()

            def _add_field(name: str, value: str) -> None:
                body.extend(f"--{boundary}\r\n".encode("utf-8"))
                body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
                body.extend((value or "").encode("utf-8"))
                body.extend(b"\r\n")

            _add_field("chat_id", str(chat_id))
            if caption:
                _add_field("caption", caption)

            filename = (file_path or "").strip().split("/")[-1] or "backup.tar.gz"
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                    "Content-Type: application/gzip\r\n\r\n"
                ).encode("utf-8")
            )
            body.extend(file_bytes)
            body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode("utf-8"))

            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            req = urllib.request.Request(
                url,
                data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(req, timeout=upload_timeout):
                pass
            return True
        except Exception as exc:
            logger.warning(
                "TG document send failed chat_id=%s file=%s: %s",
                chat_id,
                file_path,
                exc,
            )
            return False

    if run_async:
        threading.Thread(target=_send, daemon=True).start()
        return True
    return _send()
