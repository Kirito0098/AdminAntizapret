import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from core.services.telegram_webapp_init_data import verify_telegram_webapp_init_data


def _sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Строит строку initData с корректным hash (как в документации Telegram)."""
    body = dict(fields)
    data_check_string = "\n".join(f"{k}={body[k]}" for k in sorted(body.keys()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    out = dict(body)
    out["hash"] = digest
    return urlencode(out)


def test_verify_accepts_valid_init_data() -> None:
    token = "123456789:AAExampleExampleExampleExampleExample"
    auth_date = str(int(time.time()))
    user_json = '{"id":777001,"first_name":"Ada","last_name":"Lovelace","username":"ada"}'
    raw = _sign_init_data(
        {"auth_date": auth_date, "query_id": "AAQxtest", "user": user_json},
        token,
    )
    ok, err, payload = verify_telegram_webapp_init_data(
        raw, bot_token=token, max_age_seconds=3600
    )
    assert ok is True
    assert err is None
    assert payload is not None
    assert payload["id"] == "777001"
    assert payload["telegram_username"] == "ada"
    assert "Lovelace" in (payload.get("telegram_display_name") or "")


def test_verify_rejects_bad_hash() -> None:
    token = "987654321:BBExampleExampleExampleExampleExample"
    auth_date = str(int(time.time()))
    user_json = '{"id":1,"first_name":"X"}'
    raw = _sign_init_data(
        {"auth_date": auth_date, "query_id": "Q", "user": user_json},
        token,
    )
    tampered = raw.replace("hash=", "hash=0")
    ok, err, payload = verify_telegram_webapp_init_data(
        tampered, bot_token=token, max_age_seconds=3600
    )
    assert ok is False
    assert "подписи" in (err or "").lower() or "Mini App" in (err or "")
    assert payload is None


def test_verify_rejects_stale_auth_date() -> None:
    token = "111:AAAbcdabcdabcdabcdabcdabcdabcdabcda"
    old = str(int(time.time()) - 10_000)
    user_json = '{"id":42,"first_name":"Y"}'
    raw = _sign_init_data({"auth_date": old, "user": user_json}, token)
    ok, err, _payload = verify_telegram_webapp_init_data(
        raw, bot_token=token, max_age_seconds=60
    )
    assert ok is False
    assert err is not None
    assert "истек" in err or "истекло" in err


def test_verify_accepts_init_data_when_signature_in_signed_payload() -> None:
    """Клиенты Telegram могут передавать signature; оно участвует в расчёте hash вместе с остальными полями."""
    token = "222:CCCcccccccccccccccccccccccccccccccc"
    auth_date = str(int(time.time()))
    user_json = '{"id":99,"first_name":"Z"}'
    raw = _sign_init_data(
        {
            "auth_date": auth_date,
            "user": user_json,
            "signature": "dummy_signature_value_for_hmac_chain",
        },
        token,
    )
    ok, err, payload = verify_telegram_webapp_init_data(
        raw, bot_token=token, max_age_seconds=3600
    )
    assert ok is True, err
    assert payload and payload["id"] == "99"


@pytest.mark.parametrize("raw", ["", "   "])
def test_verify_rejects_empty(raw: str) -> None:
    ok, err, payload = verify_telegram_webapp_init_data(
        raw, bot_token="1:AAa", max_age_seconds=300
    )
    assert ok is False
    assert payload is None
