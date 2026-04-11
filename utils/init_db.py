#!/usr/bin/env python3
import argparse
import os
import re
import sys
from getpass import getpass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, User
from werkzeug.security import generate_password_hash


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _is_valid_username(username):
    return bool(USERNAME_PATTERN.match(username))


def _read_password_from_stdin():
    if sys.stdin is None:
        return None
    raw = sys.stdin.readline()
    if raw == "":
        return None
    return raw.rstrip("\r\n")


def _resolve_password(args, legacy_password=None):
    password_sources = 0
    if legacy_password is not None:
        password_sources += 1
    if args.password is not None:
        password_sources += 1
    if args.password_stdin:
        password_sources += 1

    if password_sources > 1:
        print(
            "Используйте только один источник пароля: legacy PASSWORD, --password или --password-stdin.",
            file=sys.stderr,
        )
        return None

    if legacy_password is not None:
        print(
            "Предупреждение: передача пароля позиционным аргументом устарела и небезопасна.",
            file=sys.stderr,
        )
        return legacy_password

    if args.password is not None:
        print(
            "Предупреждение: --password может быть виден в списке процессов.",
            file=sys.stderr,
        )
        return args.password

    if args.password_stdin:
        password = _read_password_from_stdin()
        if password is None:
            print("Не удалось прочитать пароль из stdin.", file=sys.stderr)
        return password

    if not sys.stdin.isatty():
        print("Для неинтерактивного режима используйте --password-stdin.", file=sys.stderr)
        return None

    return _prompt_password_with_confirm()


def _prompt_password_with_confirm():
    while True:
        password = getpass("Введите пароль: ").strip()
        if len(password) < 8:
            print("Пароль должен содержать минимум 8 символов!")
            continue

        password_confirm = getpass("Повторите пароль: ").strip()
        if password != password_confirm:
            print("Пароли не совпадают!")
            continue

        return password


def create_admin():
    print("\nСоздание администратора")
    print("---------------------")

    while True:
        username = input("Введите логин администратора: ").strip()
        if not username:
            print("Логин не может быть пустым!")
            continue

        if not _is_valid_username(username):
            print("Логин может содержать только буквы, цифры, '-' и '_'!")
            continue

        if User.query.filter_by(username=username).first():
            print(f"Пользователь '{username}' уже существует!")
            continue

        break

    password = _prompt_password_with_confirm()

    return username, password


def add_user(username, password, role='admin'):
    if User.query.filter_by(username=username).first():
        print(f"Пользователь '{username}' уже существует!")
        return False

    if role not in ('admin', 'viewer'):
        role = 'admin'

    if not _is_valid_username(username):
        print("Логин может содержать только буквы, цифры, '-' и '_'!")
        return False

    if len(password) < 8:
        print("Пароль должен содержать минимум 8 символов!")
        return False

    user = User(username=username, role=role)
    user.password_hash = generate_password_hash(password)
    db.session.add(user)
    db.session.commit()
    print(f"Пользователь '{username}' ({role}) успешно добавлен!")
    return True


def delete_user(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"Пользователь '{username}' не найден!")
        return False

    db.session.delete(user)
    db.session.commit()
    print(f"Пользователь '{username}' успешно удалён!")
    return True


def check_user(username):
    return User.query.filter_by(username=username).first() is not None


def list_users():
    users = User.query.all()
    if not users:
        print("Нет зарегистрированных пользователей.")
        return True

    print("Список пользователей:")
    for user in users:
        print(f"- {user.username} [{getattr(user, 'role', 'admin')}]")
    return True


def _resolve_add_user_payload(args):
    if len(args.add_user) not in (1, 2):
        print("--add-user принимает USERNAME или USERNAME PASSWORD (legacy).", file=sys.stderr)
        return None, None

    username = args.add_user[0].strip()
    if not username:
        print("Логин не может быть пустым!", file=sys.stderr)
        return None, None

    legacy_password = args.add_user[1] if len(args.add_user) == 2 else None
    password = _resolve_password(args, legacy_password=legacy_password)
    if password is None:
        return None, None

    return username, password


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Управление пользователями AdminAntizapret')
    parser.add_argument(
        '--add-user',
        nargs='+',
        metavar=('USERNAME', 'PASSWORD'),
        help='Добавить нового пользователя. Рекомендуется USERNAME + --password-stdin.',
    )
    parser.add_argument('--password', metavar='PASSWORD', help='Пароль (небезопасно: может быть виден в process list)')
    parser.add_argument('--password-stdin', action='store_true', help='Прочитать пароль из stdin')
    parser.add_argument('--role', choices=('admin', 'viewer'), default='admin', help='Роль нового пользователя')
    parser.add_argument('--delete-user', metavar='USERNAME', help='Удалить пользователя')
    parser.add_argument('--check-user', metavar='USERNAME', help='Проверить существование пользователя')
    parser.add_argument('--list-users', action='store_true', help='Вывести список пользователей')

    args = parser.parse_args()

    with app.app_context():
        db.create_all()

        if args.add_user:
            username, password = _resolve_add_user_payload(args)
            if username is None:
                sys.exit(1)

            if not add_user(username, password, role=args.role):
                sys.exit(1)
        elif args.delete_user:
            if not delete_user(args.delete_user):
                sys.exit(1)
        elif args.check_user:
            exists = check_user(args.check_user)
            sys.exit(0 if exists else 1)
        elif args.list_users:
            list_users()
        else:
            # Оригинальное интерактивное создание администратора
            if User.query.count() == 0:
                print("В системе нет пользователей")
                username, password = create_admin()

                admin = User(username=username, role='admin')
                admin.password_hash = generate_password_hash(password)
                db.session.add(admin)
                db.session.commit()

                print(f"\nСоздан администратор: {username}")
            else:
                print("\nВ базе уже есть пользователи:")
                for user in User.query.all():
                    print(f"- {user.username} [{getattr(user, 'role', 'admin')}]")

                choice = input("\nСоздать нового администратора? (y/n): ").lower()
                if choice == 'y':
                    username, password = create_admin()

                    admin = User(username=username, role='admin')
                    admin.password_hash = generate_password_hash(password)
                    db.session.add(admin)
                    db.session.commit()

                    print(f"\nСоздан новый администратор: {username}")

    print("\nГотово! База данных инициализирована.")
