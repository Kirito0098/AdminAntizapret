#!/usr/bin/env python3
import logging
import sys


def main():
    try:
        from app import app, _wg_reconcile_all_policies
    except Exception as exc:
        logging.exception("Не удалось импортировать приложение для WG/AWG policy sync: %s", exc)
        return 1

    try:
        with app.app_context():
            _wg_reconcile_all_policies(apply_runtime=True)
        return 0
    except Exception as exc:
        logging.exception("Ошибка синхронизации WG/AWG политик: %s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())

