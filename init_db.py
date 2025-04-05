#!/usr/bin/env python3
import sys
import io

# Принудительно устанавливаем UTF-8 для вывода
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from app import app, db, User
from getpass import getpass
from werkzeug.security import generate_password_hash
import argparse

def create_admin():
    print("\nСоздание администратора")
    print("---------------------")
    
    while True:
        username = input("Введите логин администратора: ").strip()
        if not username:
            print("Логин не может быть пустым!")
            continue
            
        if User.query.filter_by(username=username).first():
            print(f"Пользователь '{username}' уже существует!")
            continue
            
        break

    while True:
        password = getpass("Введите пароль: ").strip()
        if len(password) < 8:
            print("Пароль должен содержать минимум 8 символов!")
            continue
            
        password_confirm = getpass("Повторите пароль: ").strip()
        if password != password_confirm:
            print("Пароли не совпадают!")
            continue
            
        break

    return username, password

def add_user(username, password):
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"Пользователь '{username}' уже существует!")
            return False
            
        user = User(username=username)
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()
        print(f"Пользователь '{username}' успешно добавлен!")
        return True

def delete_user(username):
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"Пользователь '{username}' не найден!")
            return False
        
        db.session.delete(user)
        db.session.commit()
        print(f"Пользователь '{username}' успешно удалён!")
        return True

def check_user(username):
    with app.app_context():
        return User.query.filter_by(username=username).first() is not None

def list_users():
    with app.app_context():
        users = User.query.all()
        if not users:
            print("Нет зарегистрированных пользователей.")
            return False
        
        print("Список пользователей:")
        for user in users:
            print(f"- {user.username}")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Управление пользователями AdminAntizapret')
    parser.add_argument('--add-user', nargs=2, metavar=('USERNAME', 'PASSWORD'), help='Добавить нового пользователя')
    parser.add_argument('--delete-user', metavar='USERNAME', help='Удалить пользователя')
    parser.add_argument('--check-user', metavar='USERNAME', help='Проверить существование пользователя')
    parser.add_argument('--list-users', action='store_true', help='Вывести список пользователей')
    
    args = parser.parse_args()
    
    with app.app_context():
        db.create_all()
        
        if args.add_user:
            username, password = args.add_user
            if not add_user(username, password):
                sys.exit(1)
        elif args.delete_user:
            if not delete_user(args.delete_user):
                sys.exit(1)
        elif args.check_user:
            exists = check_user(args.check_user)
            sys.exit(0 if exists else 1)
        elif args.list_users:
            if not list_users():
                sys.exit(1)
        else:
            # Оригинальное интерактивное создание администратора
            if User.query.count() == 0:
                print("В системе нет пользователей")
                username, password = create_admin()
                
                admin = User(username=username)
                admin.password_hash = generate_password_hash(password)
                db.session.add(admin)
                db.session.commit()
                
                print(f"\nСоздан администратор: {username}")
            else:
                print("\nВ базе уже есть пользователи:")
                for user in User.query.all():
                    print(f"- {user.username}")
                
                choice = input("\nСоздать нового администратора? (y/n): ").lower()
                if choice == 'y':
                    username, password = create_admin()
                    
                    admin = User(username=username)
                    admin.password_hash = generate_password_hash(password)
                    db.session.add(admin)
                    db.session.commit()
                    
                    print(f"\nСоздан новый администратор: {username}")
    
    print("\nГотово! База данных инициализирована.")
