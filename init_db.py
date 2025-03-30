#!/usr/bin/env python3
from app import app, db, User
from getpass import getpass
from werkzeug.security import generate_password_hash

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

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        
        # Проверяем есть ли уже администраторы
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