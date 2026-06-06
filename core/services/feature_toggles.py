"""Central registry of optional modules controlled via .env toggles."""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class FeatureToggleDefinition:
    key: str
    env_key: str
    label: str
    description: str
    default: bool = True
    group: str = "background"
    icon: str = "⚙️"
    disable_hint: Optional[str] = None
    resource_impact_level: str = "low"
    resource_savings: str = ""
    cron_kind: Optional[str] = None
    endpoints: tuple[str, ...] = ()
    settings_anchors: tuple[str, ...] = ()
    index_protocol: Optional[str] = None
    index_script_options: tuple[str, ...] = ()


RESOURCE_IMPACT_LEVELS: dict[str, dict[str, str]] = {
    "minimal": {
        "label": "минимальная",
        "css_modifier": "minimal",
    },
    "low": {
        "label": "низкая",
        "css_modifier": "low",
    },
    "medium": {
        "label": "средняя",
        "css_modifier": "medium",
    },
    "high": {
        "label": "высокая",
        "css_modifier": "high",
    },
}


FEATURE_TOGGLE_GROUPS: dict[str, dict[str, str]] = {
    "background": {
        "label": "Фоновые задачи",
        "description": "Cron-задачи и фоновые потоки — разделы UI остаются доступными.",
        "badge": "Фоновая задача",
        "section_modifier": "tasks",
        "disable_hint_default": "Задача перестанет выполняться; интерфейс панели не скрывается.",
    },
    "app_module": {
        "label": "Разделы приложения",
        "description": "Полное отключение модулей: меню, страницы и связанные API.",
        "badge": "Раздел приложения",
        "section_modifier": "modules",
        "disable_hint_default": "Пункт меню скрывается; страницы и API возвращают «модуль отключён».",
    },
}

FEATURE_TOGGLES: tuple[FeatureToggleDefinition, ...] = (
    FeatureToggleDefinition(
        key="traffic_sync",
        env_key="TRAFFIC_SYNC_ENABLED",
        label="Синхронизация трафика",
        description=(
            "Cron-задача сбора статистики OpenVPN и WireGuard в базу данных "
            "(по умолчанию каждую минуту). Нужна для дашборда «Трафик (БД)» и лимитов трафика."
        ),
        icon="📊",
        disable_hint=(
            "Перестанут обновляться «Трафик (БД)» и автоматические лимиты трафика клиентов."
        ),
        resource_impact_level="high",
        resource_savings=(
            "Оценка: cron каждую минуту, отдельный Python-процесс (~30–80 МБ RAM на запуск), "
            "чтение status-логов OpenVPN/WG и запись в SQLite; кратковременный CPU ~2–5% "
            "на несколько секунд."
        ),
        default=True,
        group="background",
        cron_kind="traffic_sync",
    ),
    FeatureToggleDefinition(
        key="wg_policy_sync",
        env_key="WG_POLICY_SYNC_ENABLED",
        label="Синхронизация политик WG/AWG",
        description=(
            "Cron-задача сверки блокировок WireGuard и AmneziaWG с базой "
            "(по умолчанию каждые 2 минуты) и фоновый запуск после изменений клиентов."
        ),
        icon="🔄",
        disable_hint="Блокировки WireGuard и AmneziaWG могут расходиться с данными в панели.",
        resource_impact_level="medium",
        resource_savings=(
            "Оценка: cron каждые 2 мин + запуск после изменений клиентов; subprocess Python "
            "с reconcile WG/AWG (~40–100 МБ RAM), вызовы wg/awg; CPU ~2–8% на время синхронизации."
        ),
        default=True,
        group="background",
        cron_kind="wg_policy_sync",
    ),
    FeatureToggleDefinition(
        key="resource_monitor",
        env_key="MONITOR_ENABLED",
        label="Мониторинг нагрузки CPU/RAM",
        description=(
            "Фоновый поток проверки загрузки сервера и Telegram-уведомления "
            "о высокой нагрузке (пороги настраиваются в разделе «Пользователи»)."
        ),
        icon="📈",
        disable_hint="Telegram-оповещения о высокой нагрузке CPU/RAM перестанут отправляться.",
        resource_impact_level="low",
        resource_savings=(
            "Оценка: фоновый поток в gunicorn, psutil раз в ~60 с (1 с замер CPU); "
            "RAM пренебрежимо, CPU ~0,5–2% в среднем; без cron и дискового I/O."
        ),
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="active_web_sessions",
        env_key="ACTIVE_WEB_SESSION_TRACKING_ENABLED",
        label="Учёт активных сессий панели",
        description=(
            "Запись heartbeat активных пользователей в БД для ночного авто-перезапуска "
            "и счётчика на вкладке «Обслуживание»."
        ),
        icon="👥",
        disable_hint=(
            "Счётчик активных сессий на «Обслуживание» и ночной авто-перезапуск "
            "перестанут учитывать активность пользователей."
        ),
        resource_impact_level="low",
        resource_savings=(
            "Оценка: запись heartbeat в SQLite не чаще раза в ~30 с на активного админа; "
            "CPU минимален, диск I/O растёт с числом одновременных сессий."
        ),
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="runtime_backup_cleanup",
        env_key="RUNTIME_BACKUP_CLEANUP_ENABLED",
        label="Очистка runtime-бэкапов",
        description=(
            "Cron-задача удаления устаревших каталогов ips/runtime_backups "
            "(по умолчанию каждый час)."
        ),
        icon="🗑️",
        disable_hint="Каталоги ips/runtime_backups будут накапливаться без авто-удаления.",
        resource_impact_level="low",
        resource_savings=(
            "Оценка: cron раз в час, команда find для удаления каталогов; "
            "CPU и RAM минимальны, кратковременный диск I/O."
        ),
        default=True,
        group="background",
        cron_kind="runtime_backup_cleanup",
    ),
    FeatureToggleDefinition(
        key="openvpn",
        env_key="FEATURE_OPENVPN_ENABLED",
        label="OpenVPN",
        description=(
            "Управление клиентами OpenVPN на главной, смена групп UDP/TCP, блокировки и лимиты трафика."
        ),
        icon="🔐",
        disable_hint="Вкладки и действия OpenVPN на главной станут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки почти нет — экономия при неиспользовании: меньше API и логики "
            "на главной, без reconcile OpenVPN после правок клиентов."
        ),
        default=True,
        group="app_module",
        endpoints=("api_openvpn_client_block", "set_openvpn_group"),
        index_protocol="openvpn",
        index_script_options=("1", "2"),
    ),
    FeatureToggleDefinition(
        key="wireguard",
        env_key="FEATURE_WIREGUARD_ENABLED",
        label="WireGuard",
        description="Вкладка WireGuard на главной, политики доступа и действия с клиентами WG.",
        icon="🛡️",
        disable_hint="Вкладка WireGuard и связанные действия на главной станут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки почти нет — экономия при неиспользовании: меньше API WG "
            "на главной и фоновых reconcile после правок клиентов."
        ),
        default=True,
        group="app_module",
        endpoints=("api_wg_client_access",),
        index_protocol="wireguard",
        index_script_options=("4", "5", "7"),
    ),
    FeatureToggleDefinition(
        key="amneziawg",
        env_key="FEATURE_AMNEZIAWG_ENABLED",
        label="AmneziaWG",
        description="Вкладка AmneziaWG на главной и связанные операции с клиентами AWG.",
        icon="🛡️",
        disable_hint="Вкладка AmneziaWG и связанные действия на главной станут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки почти нет — экономия при неиспользовании: меньше API AWG "
            "на главной и фоновых reconcile после правок клиентов."
        ),
        default=True,
        group="app_module",
        index_protocol="amneziawg",
        index_script_options=("4", "5", "7"),
    ),
    FeatureToggleDefinition(
        key="logs_dashboard",
        env_key="FEATURE_LOGS_DASHBOARD_ENABLED",
        label="Подключённые клиенты",
        description="Раздел «Подключенные клиенты»: обзор сессий, статус-логи и «Трафик (БД)».",
        icon="📋",
        disable_hint="Раздел «Подключенные клиенты», статус-логи и API трафика станут недоступны.",
        resource_impact_level="low",
        resource_savings=(
            "Фоновой нагрузки нет; при открытой странице — сбор status/event-логов, "
            "кэш ~45 с, опциональный refresh. Отключение убирает тяжёлые запросы к логам и БД трафика."
        ),
        default=True,
        group="app_module",
        endpoints=(
            "logs_dashboard",
            "logs_cleanup_status_now",
            "logs_cleanup_status_schedule",
            "logs_reset_persisted_traffic",
            "logs_delete_deleted_client_traffic",
            "api_user_traffic_chart",
            "api_logs_dashboard_refresh_status",
        ),
    ),
    FeatureToggleDefinition(
        key="server_monitor",
        env_key="FEATURE_SERVER_MONITOR_ENABLED",
        label="Мониторинг сервера",
        description="Страница «Мониторинг сервера»: CPU/RAM, WebSocket и графики vnstat.",
        icon="🖥️",
        disable_hint="Страница «Мониторинг сервера» и связанные API/WebSocket будут недоступны.",
        resource_impact_level="medium",
        resource_savings=(
            "Фоновой нагрузки нет; при открытой странице — WebSocket и опрос /api/system_info "
            "каждые ~15 с, subprocess vnstat. Отключение снимает постоянные опросы, "
            "если кто-то держит страницу открытой."
        ),
        default=True,
        group="app_module",
        endpoints=("server_monitor", "api_bw", "api_system_info", "monitor_websocket"),
    ),
    FeatureToggleDefinition(
        key="routing",
        env_key="FEATURE_ROUTING_ENABLED",
        label="Маршрутизация",
        description=(
            "Раздел «Маршрутизация»: фильтры antizapret, CIDR-списки, пресеты и antifilter."
        ),
        icon="🗺️",
        disable_hint="Раздел «Маршрутизация» и все связанные API CIDR/antifilter будут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки нет; при работе с CIDR — загрузка/обновление списков, SQLite, "
            "возможны сетевые запросы к провайдерам. Отключение убирает тяжёлые операции маршрутизации."
        ),
        default=True,
        group="app_module",
        endpoints=(
            "routing",
            "get_antizapret_settings",
            "update_antizapret_settings",
            "antizapret_settings_schema",
            "api_cidr_lists",
            "api_cidr_task_status",
            "api_cidr_db_status",
            "api_cidr_db_refresh",
            "api_cidr_db_clear",
            "api_cidr_db_generate",
            "api_cidr_presets_list",
            "api_cidr_presets_create",
            "api_cidr_presets_update",
            "api_cidr_presets_delete",
            "api_cidr_presets_reset",
            "api_cidr_providers_meta",
            "api_antifilter_status",
            "api_antifilter_refresh",
            "api_antizapret_ip_files",
        ),
    ),
    FeatureToggleDefinition(
        key="edit_files",
        env_key="FEATURE_EDIT_FILES_ENABLED",
        label="Редактор файлов",
        description="Страница «Редактировать файлы» для правки конфигов и скриптов на сервере.",
        icon="📝",
        disable_hint="Страница «Редактировать файлы» будет недоступна.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки нет; нагрузка только при чтении/записи файлов через страницу."
        ),
        default=True,
        group="app_module",
        endpoints=("edit_files",),
    ),
    FeatureToggleDefinition(
        key="telegram",
        env_key="FEATURE_TELEGRAM_ENABLED",
        label="Telegram",
        description=(
            "Telegram-авторизация, Mini App (/tg-mini) и связанные API. "
            "Не влияет на Telegram-уведомления администраторам."
        ),
        icon="✈️",
        disable_hint=(
            "Вход через Telegram и Mini App будут недоступны. "
            "Уведомления администраторам не затрагиваются."
        ),
        resource_impact_level="low",
        resource_savings=(
            "Фоновой нагрузки почти нет; нагрузка при входе через Telegram и работе Mini App "
            "(HTTP-запросы к API)."
        ),
        default=True,
        group="app_module",
        endpoints=(
            "auth_telegram",
            "auth_telegram_mini",
            "tg_mini_app",
            "tg_mini_open",
            "api_tg_mini_settings_get",
            "api_tg_mini_settings_update",
            "api_tg_mini_dashboard",
            "api_tg_mini_send_config",
            "api_tg_mini_check_bot_delivery",
        ),
        settings_anchors=("telegram-auth",),
    ),
    FeatureToggleDefinition(
        key="backups",
        env_key="FEATURE_BACKUPS_ENABLED",
        label="Резервные копии",
        description=(
            "Раздел бэкапов в «Обслуживание» и API /api/backups/*. "
            "При отключении также снимается cron авто-бэкапа."
        ),
        icon="💾",
        disable_hint="Раздел бэкапов в «Обслуживание», API /api/backups/* и cron авто-бэкапа будут отключены.",
        resource_impact_level="medium",
        resource_savings=(
            "Оценка: при включённом авто-бэкапе — cron по расписанию (архивация, диск I/O, "
            "RAM ~50–150 МБ на создание); вне расписания нагрузка только при ручном бэкапе/восстановлении."
        ),
        default=True,
        group="app_module",
        endpoints=(
            "api_backups_list",
            "api_backups_settings",
            "api_backups_create",
            "api_backups_test_telegram",
            "api_backups_restore",
            "api_backups_delete",
        ),
    ),
    FeatureToggleDefinition(
        key="user_management",
        env_key="FEATURE_USER_MANAGEMENT_ENABLED",
        label="Пользователи и доступ",
        description=(
            "Вкладка «Пользователи и доступ»: учётные записи, роли, Telegram-уведомления "
            "и права viewer на конфиги."
        ),
        icon="👤",
        disable_hint=(
            "Вкладка «Пользователи и доступ» и API управления пользователями/viewer-доступом "
            "станут недоступны."
        ),
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки нет; нагрузка только при работе с пользователями и правами доступа."
        ),
        default=True,
        group="app_module",
        endpoints=("api_viewer_access", "api_monitor_settings", "api_tg_notify_test"),
        settings_anchors=("user-management",),
    ),
    FeatureToggleDefinition(
        key="security",
        env_key="FEATURE_SECURITY_ENABLED",
        label="Безопасность",
        description=(
            "Вкладка «Безопасность»: IP-ограничения, whitelist, защита от сканеров и публикация панели."
        ),
        icon="🔒",
        disable_hint="Вкладка «Безопасность» и связанные настройки IP-ограничений станут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки нет; при включённых IP-ограничениях — проверка IP на каждый запрос."
        ),
        default=True,
        group="app_module",
        settings_anchors=("security",),
    ),
    FeatureToggleDefinition(
        key="action_logs",
        env_key="FEATURE_ACTION_LOGS_ENABLED",
        label="Логи действий",
        description="Вкладка «Логи действий»: журнал действий администраторов и экспорт в CSV.",
        icon="📜",
        disable_hint="Вкладка «Логи действий» и экспорт журнала станут недоступны.",
        resource_impact_level="low",
        resource_savings=(
            "Фоновой нагрузки нет; при открытой вкладке — выборка до 300 записей из SQLite."
        ),
        default=True,
        group="app_module",
        endpoints=("api_settings_action_logs_export",),
        settings_anchors=("action-logs",),
    ),
    FeatureToggleDefinition(
        key="system_updates",
        env_key="FEATURE_SYSTEM_UPDATES_ENABLED",
        label="Обновления системы",
        description=(
            "Вкладка «Обновления»: проверка git-репозитория, просмотр CHANGELOG и фоновое обновление панели."
        ),
        icon="⬆️",
        disable_hint=(
            "Вкладка «Обновления», проверка версий и запуск обновления из панели станут недоступны."
        ),
        resource_impact_level="medium",
        resource_savings=(
            "Фоновой нагрузки нет; при проверке/обновлении — git fetch, subprocess, диск I/O "
            "и RAM ~50–200 МБ на время обновления."
        ),
        default=True,
        group="app_module",
        endpoints=("check_updates", "update_system", "api_latest_changelog"),
        settings_anchors=("system-updates",),
    ),
    FeatureToggleDefinition(
        key="diagnostics_tests",
        env_key="FEATURE_DIAGNOSTICS_TESTS_ENABLED",
        label="Тесты и диагностика",
        description="Вкладка «Тесты»: сбор и запуск pytest из веб-панели для диагностики.",
        icon="🧪",
        disable_hint="Вкладка «Тесты» и API запуска pytest станут недоступны.",
        resource_impact_level="high",
        resource_savings=(
            "Оценка: при запуске — subprocess pytest (RAM ~80–300 МБ), CPU до 50–100% "
            "на время прогона; без запуска нагрузки нет."
        ),
        default=True,
        group="app_module",
        endpoints=("api_tests_collect", "api_tests_run", "api_cidr_task_status"),
        settings_anchors=("tests",),
    ),
    FeatureToggleDefinition(
        key="qr_downloads",
        env_key="FEATURE_QR_DOWNLOADS_ENABLED",
        label="Скачивание и QR",
        description=(
            "Вкладка «Одноразовые ссылки» и выдача конфигов: скачивание, QR-коды, "
            "одноразовые ссылки и публичная раздача."
        ),
        icon="📲",
        disable_hint=(
            "Вкладка «Одноразовые ссылки», кнопки скачивания/QR на главной и связанные маршруты "
            "станут недоступны."
        ),
        resource_impact_level="low",
        resource_savings=(
            "Фоновой нагрузки нет; при скачивании/QR — чтение файлов конфигов и генерация изображений."
        ),
        default=True,
        group="app_module",
        endpoints=(
            "download",
            "generate_qr",
            "generate_one_time_download",
            "one_time_qr_download",
            "public_download",
            "toggle_public_download",
        ),
        settings_anchors=("qr-settings",),
    ),
    FeatureToggleDefinition(
        key="vpn_network",
        env_key="FEATURE_VPN_NETWORK_ENABLED",
        label="Порт, HTTPS и Nginx",
        description="Вкладка «Порт, HTTPS и Nginx»: публикация панели, порт и настройки reverse-proxy.",
        icon="🌐",
        disable_hint="Вкладка «Порт, HTTPS и Nginx» и связанные настройки публикации станут недоступны.",
        resource_impact_level="minimal",
        resource_savings=(
            "Фоновой нагрузки нет; нагрузка только при изменении настроек публикации."
        ),
        default=True,
        group="app_module",
        settings_anchors=("vpn-network",),
    ),
    FeatureToggleDefinition(
        key="maintenance",
        env_key="FEATURE_MAINTENANCE_ENABLED",
        label="Обслуживание",
        description=(
            "Раздел «Обслуживание»: ночной авто-перезапуск, счётчик сессий и перезапуск службы панели. "
            "Бэкапы управляются отдельным модулем."
        ),
        icon="🛠️",
        disable_hint=(
            "Ночной авто-перезапуск, перезапуск службы и связанные настройки в «Обслуживание» "
            "станут недоступны (бэкапы — отдельный модуль)."
        ),
        resource_impact_level="low",
        resource_savings=(
            "Оценка: cron ночного перезапуска (если включён) и subprocess при ручном рестарте службы; "
            "вне этих операций нагрузки нет."
        ),
        default=True,
        group="app_module",
        endpoints=("api_restart_service",),
        settings_anchors=("maintenance",),
    ),
)

FEATURE_TOGGLE_BY_KEY = {item.key: item for item in FEATURE_TOGGLES}
FEATURE_TOGGLE_BY_ENV = {item.env_key: item for item in FEATURE_TOGGLES}

OPENVPN_INDEX_SCRIPT_OPTIONS = frozenset(
    option
    for item in FEATURE_TOGGLES
    if item.key == "openvpn"
    for option in item.index_script_options
)
WG_AWG_INDEX_SCRIPT_OPTIONS = frozenset(
    option
    for item in FEATURE_TOGGLES
    if item.key in {"wireguard", "amneziawg"}
    for option in item.index_script_options
)


def _env_bool(get_env_value: Callable, env_key: str, default: bool) -> bool:
    fallback = "true" if default else "false"
    raw = (get_env_value(env_key, fallback) or fallback).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_feature_toggle_values(*, get_env_value) -> dict[str, bool]:
    return {
        item.key: _env_bool(get_env_value, item.env_key, item.default)
        for item in FEATURE_TOGGLES
    }


def is_feature_enabled(env_key: str, *, get_env_value, default: bool = True) -> bool:
    item = FEATURE_TOGGLE_BY_ENV.get(env_key)
    fallback_default = item.default if item is not None else default
    return _env_bool(get_env_value, env_key, fallback_default)


def app_module_disabled_message(module_key: str) -> str:
    item = FEATURE_TOGGLE_BY_KEY.get(module_key)
    label = item.label if item is not None else module_key
    return f"Раздел «{label}» отключён администратором."


def is_app_module_enabled(module_key: str, *, get_env_value) -> bool:
    item = FEATURE_TOGGLE_BY_KEY.get(module_key)
    if item is None or item.group != "app_module":
        return True
    return _env_bool(get_env_value, item.env_key, item.default)


def get_app_module_states(*, get_env_value) -> dict[str, bool]:
    return {
        item.key: is_app_module_enabled(item.key, get_env_value=get_env_value)
        for item in FEATURE_TOGGLES
        if item.group == "app_module"
    }


def build_feature_toggles_page_items(*, get_env_value) -> list[dict]:
    values = get_feature_toggle_values(get_env_value=get_env_value)
    result = []
    for item in FEATURE_TOGGLES:
        group_meta = FEATURE_TOGGLE_GROUPS[item.group]
        disable_hint = item.disable_hint or group_meta["disable_hint_default"]
        impact_meta = RESOURCE_IMPACT_LEVELS.get(
            item.resource_impact_level, RESOURCE_IMPACT_LEVELS["low"]
        )
        result.append(
            {
                "key": item.key,
                "env_key": item.env_key,
                "label": item.label,
                "description": item.description,
                "enabled": values[item.key],
                "group": item.group,
                "group_badge": group_meta["badge"],
                "icon": item.icon,
                "disable_hint": disable_hint,
                "resource_impact_level": item.resource_impact_level,
                "resource_impact_label": impact_meta["label"],
                "resource_impact_css": impact_meta["css_modifier"],
                "resource_savings": item.resource_savings,
            }
        )
    return result


def build_feature_toggles_page_groups(*, get_env_value) -> list[dict]:
    items = build_feature_toggles_page_items(get_env_value=get_env_value)
    grouped: dict[str, list[dict]] = {key: [] for key in FEATURE_TOGGLE_GROUPS}
    for item in items:
        grouped.setdefault(item["group"], []).append(item)

    result = []
    for group_key, meta in FEATURE_TOGGLE_GROUPS.items():
        group_items = grouped.get(group_key, [])
        if not group_items:
            continue
        enabled_count = sum(1 for item in group_items if item["enabled"])
        result.append(
            {
                "key": group_key,
                "label": meta["label"],
                "description": meta["description"],
                "badge": meta["badge"],
                "section_modifier": meta["section_modifier"],
                "items": group_items,
                "enabled_count": enabled_count,
                "disabled_count": len(group_items) - enabled_count,
                "total_count": len(group_items),
            }
        )
    return result


def apply_feature_toggle_settings(
    *,
    form_values: dict[str, bool],
    set_env_value,
    runtime_set,
    maintenance_scheduler_service,
    ensure_traffic_sync_cron,
    ensure_wg_policy_sync_cron,
    ensure_runtime_backup_cleanup_cron,
    ensure_app_backup_cron=None,
) -> tuple[bool, str]:
    changed: list[str] = []

    for item in FEATURE_TOGGLES:
        enabled = bool(form_values.get(item.key, item.default))
        env_value = "true" if enabled else "false"
        set_env_value(item.env_key, env_value)
        runtime_set(item.env_key, enabled)
        changed.append(f"{item.key}={'вкл' if enabled else 'выкл'}")

        if item.env_key == "TRAFFIC_SYNC_ENABLED":
            maintenance_scheduler_service.traffic_sync_enabled = enabled
        elif item.env_key == "WG_POLICY_SYNC_ENABLED":
            maintenance_scheduler_service.wg_policy_sync_enabled = enabled
        elif item.env_key == "RUNTIME_BACKUP_CLEANUP_ENABLED":
            maintenance_scheduler_service.runtime_backup_cleanup_enabled = enabled
        elif item.env_key == "FEATURE_BACKUPS_ENABLED" and not enabled:
            set_env_value("APP_BACKUP_ENABLED", "false")
            runtime_set("APP_BACKUP_ENABLED", False)

    cron_messages: list[str] = []
    for ensure_fn, label in (
        (ensure_traffic_sync_cron, "синхронизация трафика"),
        (ensure_wg_policy_sync_cron, "синхронизация WG/AWG"),
        (ensure_runtime_backup_cleanup_cron, "очистка runtime-бэкапов"),
    ):
        ok, message = ensure_fn()
        if not ok:
            return False, message
        cron_messages.append(f"{label}: {message}")

    if ensure_app_backup_cron is not None:
        ok, message = ensure_app_backup_cron()
        if not ok:
            return False, message
        cron_messages.append(f"авто-бэкап: {message}")

    details = ", ".join(changed)
    if cron_messages:
        details = f"{details}; cron: {'; '.join(cron_messages)}"
    return True, details
