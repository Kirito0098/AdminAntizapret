import os
import logging


logger = logging.getLogger(__name__)

workers = int(os.getenv('GUNICORN_WORKERS', 1))
bind = f'{os.getenv("BIND", "0.0.0.0")}:{os.getenv("APP_PORT", "5050")}'
worker_class = "gthread"
threads = 8
timeout = 300
graceful_timeout = 300
keepalive = 2
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', 1200))
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', 120))
errorlog = '-'
accesslog = '-'

if os.getenv('USE_HTTPS', 'false').lower() == 'true':
    certfile = os.getenv('SSL_CERT')
    keyfile = os.getenv('SSL_KEY')
    if certfile and keyfile:
        ssl_options = {'certfile': certfile, 'keyfile': keyfile}
    else:
        logger.warning("HTTPS включен, но сертификаты не найдены. Используется HTTP.")
