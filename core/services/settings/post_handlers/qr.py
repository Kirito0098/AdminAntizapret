import os


def handle_qr_settings(form, *, flash, get_env_value, set_env_value, log_user_action_event):
    ttl_raw = form.get("qr_download_token_ttl_seconds", "").strip()
    if ttl_raw:
        if ttl_raw.isdigit():
            ttl_value = int(ttl_raw)
            if 60 <= ttl_value <= 3600:
                old_ttl = (get_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", "600") or "600").strip()
                set_env_value("QR_DOWNLOAD_TOKEN_TTL_SECONDS", str(ttl_value))
                os.environ["QR_DOWNLOAD_TOKEN_TTL_SECONDS"] = str(ttl_value)
                flash("TTL одноразовой QR-ссылки обновлен", "success")
                log_user_action_event(
                    "settings_qr_ttl_update",
                    target_type="qr",
                    target_name="QR_DOWNLOAD_TOKEN_TTL_SECONDS",
                    details=f"{old_ttl} → {ttl_value}с",
                )
            else:
                flash("TTL QR-ссылки должен быть в диапазоне 60..3600 секунд", "error")
        else:
            flash("TTL QR-ссылки должен быть целым числом", "error")

    max_downloads_raw = form.get("qr_download_token_max_downloads", "").strip()
    if max_downloads_raw:
        if max_downloads_raw.isdigit() and int(max_downloads_raw) in (1, 3, 5):
            old_max_dl = (get_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", "1") or "1").strip()
            set_env_value("QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS", max_downloads_raw)
            os.environ["QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS"] = max_downloads_raw
            flash("Лимит скачиваний одноразовой ссылки обновлен", "success")
            log_user_action_event(
                "settings_qr_max_downloads_update",
                target_type="qr",
                target_name="QR_DOWNLOAD_TOKEN_MAX_DOWNLOADS",
                details=f"{old_max_dl} → {max_downloads_raw}",
            )
        else:
            flash("Лимит скачиваний должен быть одним из значений: 1, 3 или 5", "error")

    clear_pin = form.get("clear_qr_download_pin") == "on"
    pin_raw = (form.get("qr_download_pin") or "").strip()
    if clear_pin:
        set_env_value("QR_DOWNLOAD_PIN", "")
        os.environ["QR_DOWNLOAD_PIN"] = ""
        flash("PIN для QR-ссылок очищен", "success")
        log_user_action_event(
            "settings_qr_pin_clear",
            target_type="qr",
            target_name="QR_DOWNLOAD_PIN",
        )
    elif pin_raw:
        if pin_raw.isdigit() and 4 <= len(pin_raw) <= 12:
            set_env_value("QR_DOWNLOAD_PIN", pin_raw)
            os.environ["QR_DOWNLOAD_PIN"] = pin_raw
            flash("PIN для QR-ссылок обновлен", "success")
            log_user_action_event(
                "settings_qr_pin_update",
                target_type="qr",
                target_name="QR_DOWNLOAD_PIN",
                details=f"length={len(pin_raw)}",
            )
        else:
            flash("PIN должен содержать только цифры и иметь длину от 4 до 12", "error")
    return None
