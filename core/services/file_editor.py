import logging


logger = logging.getLogger(__name__)


class FileEditor:
    def __init__(self):
        self.files = {
            "include_hosts": "/root/antizapret/config/include-hosts.txt",
            "exclude_hosts": "/root/antizapret/config/exclude-hosts.txt",
            "include_ips": "/root/antizapret/config/include-ips.txt",
            "allow-ips": "/root/antizapret/config/allow-ips.txt",
            "exclude-ips": "/root/antizapret/config/exclude-ips.txt",
            "forward-ips": "/root/antizapret/config/forward-ips.txt",
            "include-adblock-hosts": "/root/antizapret/config/include-adblock-hosts.txt",
            "exclude-adblock-hosts": "/root/antizapret/config/exclude-adblock-hosts.txt",
            "remove-hosts": "/root/antizapret/config/remove-hosts.txt",
        }

    def update_file_content(self, file_type, content):
        if file_type in self.files:
            try:
                with open(self.files[file_type], "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            except OSError as e:
                logger.exception("Ошибка записи в файл %s: %s", self.files[file_type], e)
                return False
        return False

    def get_file_contents(self):
        file_contents = {}
        for key, path in self.files.items():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_contents[key] = f.read()
            except FileNotFoundError:
                file_contents[key] = ""
        return file_contents
