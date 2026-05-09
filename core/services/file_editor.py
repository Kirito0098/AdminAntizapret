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
            "drop-ips": "/root/antizapret/config/drop-ips.txt",
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

    def get_file_display_titles(self):
        titles = {}
        for key, path in self.files.items():
            fallback_title = key.replace("_", " ").replace("-", " ").title()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
            except OSError:
                titles[key] = fallback_title
                continue

            if not first_line:
                titles[key] = fallback_title
                continue

            if first_line.startswith("#"):
                normalized = first_line.lstrip("#").strip()
            else:
                normalized = first_line

            titles[key] = normalized or fallback_title

        return titles
