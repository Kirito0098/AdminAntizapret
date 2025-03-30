# AdminAntizapret

## Описание
**AdminAntizapret** — это веб-приложение, разработанное как дополнение к проекту [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN). Оно предназначено для управления конфигурациями VPN-клиентов, включая добавление и удаление конфигураций для OpenVPN, AmneziaWG и WireGuard.

## Основные возможности
- Добавление новых клиентов для OpenVPN, WireGuard и AmneziaWG.
- Удаление существующих клиентов.
- Скачивание конфигурационных файлов для клиентов.
- Удобный веб-интерфейс для управления.
- Панель управления службой через `adminpanel.sh`.

## Установка

### Основной метод
Для автоматической установки выполните следующую команду:
```bash
bash <(wget --no-hsts -qO- https://raw.githubusercontent.com/Kirito0098/AdminAntizapret/refs/heads/main/adminpanel.sh)
```
Приложение будет доступно по адресу: `http://Ваш IP: Порт который указали при установке`.
Приложение будет установлено в директорию `/opt/AdminAntizapret/`.

### Альтернативный метод
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
   venv\Scripts\activate     # Для Windows
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

6. Приложение будет доступно по адресу: `http://Ваш IP:5050`.

## Использование
1. Перейдите на страницу входа и войдите с учетными данными администратора.
2. На главной странице вы можете:
   - Добавлять новых клиентов.
   - Удалять существующих клиентов.
   - Скачивать конфигурационные файлы для OpenVPN, WireGuard и AmneziaWG.
3. Для добавления клиента укажите имя клиента и срок действия сертификата (для OpenVPN).

## Панель управления
Для управления службой используйте скрипт `adminpanel.sh`. Основное меню панели включает:
- Перезапуск сервиса.
- Проверка статуса сервиса.
- Просмотр логов.
- Проверка обновлений.
- Тестирование работы.
- Создание резервной копии.
- Восстановление из резервной копии.
- Добавление пользователя.
- Удаление AdminAntizapret.

Для запуска панели выполните:
```bash
sudo ./adminpanel.sh
```

## Скрипты
- **`adminpanel.sh`**: Скрипт для установки, обновления и управления сервисом AdminAntizapret.
- **`client.sh`**: Скрипт для управления клиентами (добавление, удаление, генерация конфигураций).

## Требования
- Установленный [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).
- Доступ к серверу с правами администратора.

## Лицензия
Этот проект распространяется под лицензией MIT. Подробности см. в файле `LICENSE`.

## Благодарности
- [GubernievS](https://github.com/GubernievS) за проект [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN).
