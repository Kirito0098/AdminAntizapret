import os

workers = int(os.getenv('GUNICORN_WORKERS', 4))
bind = f'{os.getenv("BIND", "0.0.0.0")}:{os.getenv("APP_PORT", "5050")}'
worker_class = "gthread"
threads = 8       
timeout = 300
graceful_timeout = 300
keepalive = 2
errorlog = '-'
accesslog = '-'

if os.getenv('USE_HTTPS', 'false').lower() == 'true':
    certfile = os.getenv('SSL_CERT')
    keyfile = os.getenv('SSL_KEY')
    if certfile and keyfile:
        ssl_options = {'certfile': certfile, 'keyfile': keyfile}
    else:
        print("Предупреждение: HTTPS включен, но сертификаты не найдены. Используется HTTP.")
