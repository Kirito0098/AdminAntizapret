import os
import logging
from functools import wraps

from flask import abort
from werkzeug.exceptions import HTTPException


logger = logging.getLogger(__name__)


class FileValidator:
    def __init__(self, config_paths, fallback_openvpn_folders=None):
        self.config_paths = config_paths
        self.fallback_openvpn_folders = list(fallback_openvpn_folders or [])

    def validate_file(self, func):
        @wraps(func)
        def wrapper(file_type, filename, *args, **kwargs):
            try:
                if file_type not in self.config_paths:
                    abort(400, description="Недопустимый тип файла")

                def _scan(dirs):
                    for config_dir in dirs:
                        for root, _, files in os.walk(config_dir):
                            for file in files:
                                if file.replace("(", "").replace(")", "") == filename.replace("(", "").replace(")", ""):
                                    return os.path.join(root, file), file.replace("(", "").replace(")", "")
                    return None, None

                file_path, clean_name = _scan(self.config_paths[file_type])
                if not file_path and file_type == "openvpn" and self.fallback_openvpn_folders:
                    file_path, clean_name = _scan(self.fallback_openvpn_folders)
                if file_path:
                    return func(file_path, clean_name, *args, **kwargs)
                abort(404, description="Файл не найден")
            except HTTPException:
                raise
            except OSError as e:
                logger.exception("Ошибка валидации файла: %s", e)
                abort(500)

        return wrapper
