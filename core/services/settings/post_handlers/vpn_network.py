import os
import platform
import subprocess


def handle_vpn_network_port(form, *, flash, get_env_value, set_env_value, log_user_action_event):
    new_port_raw = (form.get("port") or "").strip()
    if not new_port_raw:
        return None

    if new_port_raw.isdigit() and 1 <= int(new_port_raw) <= 65535:
        old_port = (get_env_value("APP_PORT", os.getenv("APP_PORT", "5050")) or "5050").strip()
        set_env_value("APP_PORT", new_port_raw)
        os.environ["APP_PORT"] = new_port_raw
        flash("Порт успешно изменён. Перезапуск службы...", "success")
        log_user_action_event(
            "settings_port_update",
            target_type="app",
            target_name="APP_PORT",
            details=f"{old_port} → {new_port_raw}",
        )

        try:
            if platform.system() == "Linux":
                subprocess.run(
                    ["systemctl", "restart", "admin-antizapret.service"], check=True
                )
        except subprocess.CalledProcessError as e:
            flash(f"Ошибка при перезапуске службы: {e}", "error")
    else:
        flash("Порт должен быть целым числом в диапазоне 1..65535", "error")
    return None
