"""Утилиты для работы с временем (timezone-aware UTC).

После отказа от устаревшего ``datetime.utcnow()`` (Python 3.12+) свежие
метки времени создаются как timezone-aware UTC через
``datetime.now(timezone.utc)``. При этом значения, прочитанные из БД
(колонки ``db.DateTime`` без ``timezone=True``), возвращаются как naive.
Сравнение naive и aware datetime бросает ``TypeError``, поэтому при
сравнении/вычитании значений из БД с ``now`` их нужно приводить к aware
через :func:`as_utc`.
"""

from datetime import datetime, timezone


def as_utc(value):
    """Приводит datetime к timezone-aware UTC.

    ``None`` остаётся ``None``. Naive-значения считаем UTC (так их пишет
    приложение) и навешиваем tzinfo; aware-значения переводим в UTC.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
