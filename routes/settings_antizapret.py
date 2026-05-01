# routes/settings_antizapret.py

import re
from flask import jsonify, request, current_app, session

from config.antizapret_params import ANTIZAPRET_PARAMS
from core.services.telegram_mini_session import has_telegram_mini_session

FILE_PATH = "/root/antizapret/setup"


def normalize_flag(v):
    if isinstance(v, (bool, int)):
        return "y" if v else "n"
    s = str(v).lower().strip()
    return "y" if s in ("y", "yes", "true", "1", "on") else "n"


def init_antizapret(app_or_bp):
    """Регистрирует все antizapret-роуты на переданный app или blueprint"""

    @app_or_bp.route("/get_antizapret_settings")
    #@auth_manager.login_required  # если нужна авторизация
    def get_antizapret_settings():
        try:
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            settings = {}
            for p in ANTIZAPRET_PARAMS:
                key, env, typ, default = p["key"], p["env"], p["type"], p["default"]
                if typ == "string":
                    m = re.search(rf"^{re.escape(env)}=(.+)$", content, re.M | re.I)
                    settings[key] = m.group(1).strip() if m else default
                else:
                    m = re.search(rf"^{re.escape(env)}=([yn])$", content, re.M | re.I)
                    settings[key] = m.group(1).lower() if m else default

            return jsonify(settings)

        except Exception as e:
            current_app.logger.error(f"Ошибка чтения настроек antizapret: {e}", exc_info=True)
            return jsonify({"error": "Ошибка чтения настроек"}), 500


    @app_or_bp.route("/update_antizapret_settings", methods=["POST"])
    #@auth_manager.login_required
    def update_antizapret_settings():
        try:
            new_settings = request.get_json(silent=True) or {}
            if not isinstance(new_settings, dict):
                return jsonify({"success": False, "message": "Ожидается JSON-объект"}), 400

            with open(FILE_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()

            desired = {}
            for p in ANTIZAPRET_PARAMS:
                if (k := p["key"]) in new_settings:
                    v = new_settings[k]
                    env = p["env"]
                    desired[env] = normalize_flag(v) if p["type"] == "flag" else str(v).strip()

            if not desired:
                return jsonify({"success": True, "message": "Нечего обновлять", "changes": 0})

            new_lines = []
            found = set()
            changes = 0

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    new_lines.append(line)
                    continue

                key_part = stripped.split("=", 1)[0].strip()
                if key_part in desired:
                    val = desired[key_part]
                    comment = " " + stripped.split("#", 1)[1].strip() if "#" in stripped else ""
                    new_lines.append(f"{key_part}={val}{comment}\n")
                    found.add(key_part)
                    changes += 1
                else:
                    new_lines.append(line)

            # Добавляем отсутствующие параметры в конец
            for env, val in desired.items():
                if env not in found:
                    new_lines.append(f"{env}={val}\n")
                    changes += 1

            has_mini_session = has_telegram_mini_session(session)

            if changes > 0:
                with open(FILE_PATH, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                user_action_logger = current_app.config.get("USER_ACTION_AUDIT_LOGGER")
                if callable(user_action_logger):
                    changed_keys = sorted(desired.keys())
                    sample = ",".join(changed_keys[:8])
                    if len(changed_keys) > 8:
                        sample += ",..."
                    details_text = f"changes={changes} keys={sample}"
                    if has_mini_session:
                        details_text += " via=tg-mini"
                    user_action_logger(
                        "settings_antizapret_update",
                        target_type="antizapret",
                        target_name="setup",
                        details=details_text,
                    )

            if changes > 0 and has_mini_session:
                logger_callback = current_app.config.get("TELEGRAM_AUDIT_LOGGER")
                if callable(logger_callback):
                    changed_keys = sorted(desired.keys())
                    sample = ",".join(changed_keys[:8])
                    if len(changed_keys) > 8:
                        sample += ",..."
                    logger_callback(
                        "mini_antizapret_settings_update",
                        details=f"changes={changes} keys={sample}",
                    )

            return jsonify({
                "success": True,
                "message": "Настройки сохранены",
                "changes": changes,
                "needs_apply": True
            })

        except PermissionError:
            return jsonify({"success": False, "message": "Нет прав на запись"}), 403
        except Exception as e:
            current_app.logger.error(f"Ошибка обновления antizapret: {e}", exc_info=True)
            return jsonify({"success": False, "message": "Ошибка сервера"}), 500


    @app_or_bp.route("/antizapret_settings_schema")
    #@auth_manager.login_required
    def antizapret_settings_schema():
        return jsonify([
            {
                "key": p["key"],
                "html_id": p["html_id"],
                "type": p["type"],
                "env": p.get("env", ""),
                "param_label": p.get("param_label", p.get("env", "")),
                "title": p.get("title", ""),
                "description": p.get("description", ""),
            }
            for p in ANTIZAPRET_PARAMS
        ])
