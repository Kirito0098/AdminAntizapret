from core.services.settings.telegram_normalize import normalize_ip_entry


def handle_security_settings(form, *, flash, ip_restriction, log_user_action_event):
    ip_action_values = form.getlist("ip_action")
    if "clear_scanner_bans" in ip_action_values:
        ip_action = "clear_scanner_bans"
    elif "unban_scanner_ip" in ip_action_values:
        ip_action = "unban_scanner_ip"
    else:
        ip_action = ip_action_values[0] if ip_action_values else form.get("ip_action")

    if ip_action == "add_ip":
        new_ip = form.get("new_ip", "").strip()
        if new_ip:
            if ip_restriction.add_ip(new_ip):
                flash(f"IP {new_ip} добавлен", "success")
                log_user_action_event(
                    "settings_ip_add",
                    target_type="ip_restriction",
                    target_name=new_ip,
                )
            else:
                flash("Неверный формат IP", "error")

    elif ip_action == "remove_ip":
        ip_to_remove = form.get("ip_to_remove", "").strip()
        if ip_to_remove:
            if ip_restriction.remove_ip(ip_to_remove):
                flash(f"IP {ip_to_remove} удален", "success")
                log_user_action_event(
                    "settings_ip_remove",
                    target_type="ip_restriction",
                    target_name=ip_to_remove,
                )
            else:
                flash("IP не найден", "error")

    elif ip_action == "clear_all_ips":
        ip_restriction.clear_all()
        flash("Все IP ограничения сброшены (доступ разрешен всем)", "success")
        log_user_action_event(
            "settings_ip_clear",
            target_type="ip_restriction",
            target_name="all",
        )

    elif ip_action == "save_scanner_block":
        if not ip_restriction.is_enabled():
            flash("Сначала включите IP-ограничения", "error")
        else:
            block_scanners = form.get("block_scanners") == "true"
            block_ip_blocked_dwell = form.get("block_ip_blocked_dwell") == "true"
            try:
                max_attempts = int(form.get("scanner_max_attempts", ip_restriction.scanner_max_attempts))
                window_seconds = int(form.get("scanner_window_seconds", ip_restriction.scanner_window_seconds))
                ban_seconds = int(form.get("scanner_ban_seconds", ip_restriction.scanner_ban_seconds))
                ip_blocked_dwell_seconds = int(
                    form.get(
                        "ip_blocked_dwell_seconds",
                        ip_restriction.ip_blocked_dwell_seconds,
                    )
                )
            except (TypeError, ValueError):
                flash("Некорректные параметры блокировки сканеров", "error")
            else:
                ip_restriction.set_scanner_protection(
                    enabled=block_scanners,
                    max_attempts=max_attempts,
                    window_seconds=window_seconds,
                    ban_seconds=ban_seconds,
                    block_ip_blocked_dwell=block_ip_blocked_dwell,
                    ip_blocked_dwell_seconds=ip_blocked_dwell_seconds,
                )
                state = "включена" if block_scanners else "выключена"
                dwell_state = "включён" if block_ip_blocked_dwell else "выключен"
                flash(
                    f"Защита от сканеров {state}. Бан за пребывание на странице блокировки: {dwell_state}.",
                    "success",
                )
                log_user_action_event(
                    "settings_ip_scanner_block",
                    target_type="ip_restriction",
                    target_name="scanner_block",
                    details=(
                        f"enabled={1 if block_scanners else 0};"
                        f"max={ip_restriction.scanner_max_attempts};"
                        f"window={ip_restriction.scanner_window_seconds};"
                        f"ban={ip_restriction.scanner_ban_seconds};"
                        f"dwell={1 if block_ip_blocked_dwell else 0};"
                        f"dwell_sec={ip_restriction.ip_blocked_dwell_seconds}"
                    ),
                )

    elif ip_action == "clear_scanner_bans":
        ip_restriction.clear_scanner_bans()
        flash("Все баны сканеров сброшены (файл и iptables)", "success")
        log_user_action_event(
            "settings_ip_scanner_bans_clear",
            target_type="ip_restriction",
            target_name="scanner_bans",
        )

    elif ip_action == "unban_scanner_ip":
        ip_to_unban = form.get("ip_to_unban", "").strip()
        if ip_to_unban:
            if ip_restriction.unban_scanner_ip(ip_to_unban):
                flash(
                    f"IP {ip_to_unban} разблокирован на сервере (iptables). "
                    f"Повторный серверный бан отложен — можно тестировать без whitelist.",
                    "success",
                )
                log_user_action_event(
                    "settings_ip_scanner_unban",
                    target_type="ip_restriction",
                    target_name=ip_to_unban,
                )
            else:
                flash("Некорректный IP для разблокировки", "error")
        else:
            flash("Укажите IP для разблокировки", "error")

    elif ip_action == "enable_ips":
        ips_text = form.get("ips_text", "").strip()
        if ips_text:
            raw_entries = [ip.strip() for ip in ips_text.split(",") if ip.strip()]
            normalized_entries = []
            invalid_entries = []

            for raw_entry in raw_entries:
                normalized_entry = normalize_ip_entry(raw_entry)
                if normalized_entry is None:
                    invalid_entries.append(raw_entry)
                else:
                    normalized_entries.append(normalized_entry)

            if invalid_entries:
                invalid_preview = ", ".join(invalid_entries[:5])
                if len(invalid_entries) > 5:
                    invalid_preview += ", ..."
                flash(
                    f"Обнаружены некорректные IP/подсети: {invalid_preview}. Исправьте список и повторите.",
                    "error",
                )
            elif not normalized_entries:
                flash("Укажите хотя бы один корректный IP-адрес", "error")
            else:
                unique_entries = sorted(set(normalized_entries))
                ip_restriction.allowed_ips = set(unique_entries)
                ip_restriction.enabled = True
                ip_restriction.save_to_env()
                flash("IP ограничения включены", "success")
                log_user_action_event(
                    "settings_ip_bulk_enable",
                    target_type="ip_restriction",
                    target_name="bulk",
                    details=f"entries={len(unique_entries)}",
                )
        else:
            flash("Укажите хотя бы один IP-адрес", "error")

    return None
