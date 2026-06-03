"""Общая конфигурация pytest: корень проекта в PYTHONPATH."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Переменные, которые тесты выставляют через patch.dict(..., clear=True) или .env на сервере,
# не должны «протекать» между тестами и ломать CI (чистый runner без .env).
_GAME_ROUTE_LIMIT_ENV_KEYS = (
    "AZ_GAME_DISABLE_CONFIG_ROUTE_LIMIT",
    "AZ_GAME_CONFIG_ROUTE_LIMIT_RISK_ACK",
)


@pytest.fixture(autouse=True)
def _isolate_game_route_limit_env(monkeypatch):
    for key in _GAME_ROUTE_LIMIT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
