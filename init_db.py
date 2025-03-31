#!/usr/bin/env python3
from app import app, db, User
from getpass import getpass
from werkzeug.security import generate_password_hash
import argparse
import sys

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

def check_user(username):
    with app.app_context():
        return User.query.filter_by(username=username).first() is not None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Управление пользователями AdminAntizapret')
    parser.add_argument('--add-user', nargs=2, metavar=('USERNAME', 'PASSWORD'), help='Добавить нового пользователя')
    parser.add_argument('--check-user', metavar='USERNAME', help='Проверить существование пользователя')
    
    args = parser.parse_args()
    
    with app.app_context():
        db.create_all()
        
        if args.add_user:
            username, password = args.add_user
            if not add_user(username, password):
                sys.exit(1)
        elif args.check_user:
            exists = check_user(args.check_user)
            sys.exit(0 if exists else 1)
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