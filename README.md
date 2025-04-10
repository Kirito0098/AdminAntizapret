# AdminAntizapret
![Version](https://img.shields.io/badge/version-1.0.3-blue)
![Stars](https://img.shields.io/github/stars/Kirito0098/AdminAntizapret?style=social)
![Forks](https://img.shields.io/github/forks/Kirito0098/AdminAntizapret?style=social)
![License](https://img.shields.io/badge/license-MIT-green)
![Last Commit](https://img.shields.io/github/last-commit/Kirito0098/AdminAntizapret)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04-lightgrey)
![Tech](https://img.shields.io/badge/tech-Flask%20%7C%20SQLAlchemy%20%7C%20Python-blue)

## 📑 Оглавление
- [AdminAntizapret](#adminantizapret)
  - [📑 Оглавление](#-оглавление)
  - [📝 Описание](#-описание)
  - [🚀 Быстрый старт](#-быстрый-старт)
  - [✨ Основные возможности](#-основные-возможности)
  - [⚙️ Установка](#️-установка)
    - [Основной метод](#основной-метод)
    - [Процесс установки](#процесс-установки)
    - [Альтернативный метод](#альтернативный-метод)
  - [🖥 Использование](#-использование)
  - [🔧 Панель управления](#-панель-управления)
  - [📜 Скрипты](#-скрипты)
  - [📋 Требования](#-требования)
    - [Минимальные характеристики:](#минимальные-характеристики)
  - [📄 Лицензия](#-лицензия)
  - [🙏 Благодарности](#-благодарности)
  - [💖 Поддержка проекта](#-поддержка-проекта)
  - [📜 История изменений](#-история-изменений)

## 📝 Описание
**AdminAntizapret** — это веб-приложение, разработанное как дополнение к проекту [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN). Оно предназначено для управления конфигурациями VPN-клиентов, включая добавление и удаление конфигураций для OpenVPN, AmneziaWG и WireGuard.

## 🚀 Быстрый старт
1. Установите через `adminpanel.sh`:
   ```bash
   bash <(wget -qO- https://raw.githubusercontent.com/Kirito0098/AdminAntizapret/refs/heads/main/adminpanel.sh)
   ```
2. Перейдите в браузере по адресу `http://<ваш-сервер>:5050`.
3. Войдите с учетными данными администратора, созданными при установке.

## ✨ Основные возможности
- Добавление новых клиентов для OpenVPN, WireGuard и AmneziaWG.
- Удаление существующих клиентов.
- Скачивание конфигурационных файлов для клиентов.
- Удобный веб-интерфейс для управления.
- Панель управления службой через `adminpanel.sh`.
- **Редактирование конфигурационных файлов AntiZapret (включение/исключение хостов и IP-адресов).**

![Редактирование конфигурационных файлов AntiZapret](https://github.com/user-attachments/assets/e4c9646f-981d-4cf6-8a0c-ffb2847e9f09)  
*Рисунок 6: Редактирование конфигурационных файлов AntiZapret через веб-интерфейс.*

## ⚙️ Установка

### Основной метод
Для автоматической установки выполните следующую команду:
```bash
bash <(wget --no-hsts -qO- https://raw.githubusercontent.com/Kirito0098/AdminAntizapret/refs/heads/main/adminpanel.sh)
```
Приложение будет установлено в директорию `/opt/AdminAntizapret/`.

> **Примечание:** Скрипт `adminpanel.sh` автоматически проверяет, установлен ли [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN). Если он отсутствует, скрипт предложит установить его перед продолжением.

![Запрос на установку через adminpanel.sh](https://github.com/user-attachments/assets/883914ed-59cb-454a-bea1-69917b1ecdba)  
*Рисунок 1: Запрос на установку через adminpanel.sh — начальный этап установки.*

### Процесс установки
Ниже показан пример процесса установки через `adminpanel.sh`:

![Процесс установки через adminpanel.sh](https://github.com/user-attachments/assets/16af7b08-ab40-488b-ad93-2d7c51cf4f09)  
*Рисунок 2: Процесс установки через adminpanel.sh — выполнение шагов установки.*

### Альтернативный метод
> **Предупреждение:** Этот метод предназначен только для опытных пользователей. Используйте его, если вы понимаете, как вручную управлять зависимостями и настройками.

1. Убедитесь, что у вас установлены следующие зависимости:
   - Python 3.6+.
   - Git.
   - OpenVPN, WireGuard и другие зависимости, необходимые для работы [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).

2. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Kirito0098/AdminAntizapret.git
   cd AdminAntizapret
   ```

3. Установите виртуальное окружение и зависимости:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Для Linux/MacOS
   pip install -r requirements.txt
   ```

4. Инициализируйте базу данных:
   ```bash
   python init_db.py
   ```

5. Запустите приложение:
   ```bash
   python app.py
   ```

6. Приложение будет доступно по адресу: `http://localhost:5050`.

## 🖥 Использование
1. Перейдите на страницу входа и войдите с учетными данными администратора.
   
   ![Форма авторизации](https://github.com/user-attachments/assets/4f95b717-8864-432f-aa87-82fbeb0ce148)  
   *Рисунок 3: Форма авторизации — вход в систему.*

2. На главной странице вы можете:
   - Добавлять новых клиентов.
   - Удалять существующих клиентов.
   - Скачивать конфигурационные файлы для OpenVPN, WireGuard и AmneziaWG.

   ![Веб-панель управления](https://github.com/user-attachments/assets/e450429a-364a-49fe-9e1f-5b0e6d28698c)  
   *Рисунок 4: Веб-панель управления — управление клиентами и конфигурациями.*

3. Для добавления клиента укажите имя клиента и срок действия сертификата (для OpenVPN).

## 🔧 Панель управления
Для управления службой используйте скрипт `adminpanel.sh`. Основное меню панели включает:
1. Добавить администратора.
2. Перезапустить сервис.
3. Проверить статус сервиса.
4. Просмотреть логи.
5. Проверить обновления.
6. Протестировать работу.
7. Создать резервную копию.
8. Восстановить из резервной копии.
9. Удалить AdminAntizapret.
10. Проверить и установить права.

Панель управления находится в директории `/root/adminpanel`.

![Панель управления](https://github.com/user-attachments/assets/c7618626-6f35-469d-a0b4-56b516e5328d)  
*Рисунок 5: Панель управления — основные функции управления сервисом.*

Для запуска панели выполните:
```bash
sudo ./adminpanel.sh
```

## 📜 Скрипты
- **`adminpanel.sh`**: Скрипт для установки, обновления и управления сервисом AdminAntizapret. Также проверяет наличие [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN) и предлагает установить его, если он отсутствует.
- **`client.sh`**: Скрипт для управления клиентами (добавление, удаление, генерация конфигураций).

## 📋 Требования

### Минимальные характеристики:
- **ОС**: Ubuntu 20.04 LTS 
- **Процессор**: 1 ядро (x86_64)
- **Оперативная память**: 512 МБ
- **Дисковое пространство**: 2 ГБ (для установки зависимостей и хранения конфигураций)
- **Сеть**: Публичный IP-адрес или доступ к интернету
- **Порты**: Свободный TCP-порт (по умолчанию `5050`)
  - Установленный [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN)
  - Права root/sudo для управления сервисом

## 📄 Лицензия
Этот проект распространяется под лицензией MIT. Подробности см. в файле `LICENSE`.

## 🙏 Благодарности
- [GubernievS](https://github.com/GubernievS) за проект [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).

## 💖 Поддержка проекта
Поблагодарить и поддержать проект можно на:

[cloudtips.ru](https://pay.cloudtips.ru/p/f556e032)

## 📜 История изменений
Подробности о последних изменениях и версиях можно найти в [CHANGELOG.md](./CHANGELOG.md).
