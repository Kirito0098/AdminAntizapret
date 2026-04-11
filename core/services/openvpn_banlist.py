class OpenVPNBanlistService:
    def __init__(self, *, banned_clients_file, client_connect_script, client_connect_ban_check_block):
        self.banned_clients_file = banned_clients_file
        self.client_connect_script = client_connect_script
        self.client_connect_ban_check_block = client_connect_ban_check_block

    def read_banned_clients(self):
        banned = set()
        try:
            with open(self.banned_clients_file, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    banned.add(line)
        except FileNotFoundError:
            return set()
        return banned

    def write_banned_clients(self, clients):
        ordered = sorted(set(clients), key=str.lower)
        with open(self.banned_clients_file, "w", encoding="utf-8") as f:
            if ordered:
                f.write("\n".join(ordered) + "\n")

    def ensure_client_connect_ban_check_block(self):
        """Ensure banned_clients check is present in client-connect.sh."""
        try:
            with open(self.client_connect_script, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            content = ""

        if self.client_connect_ban_check_block in content:
            return

        if content.startswith("#!"):
            first_line_end = content.find("\n")
            if first_line_end == -1:
                shebang_line = content + "\n"
                rest = ""
            else:
                shebang_line = content[: first_line_end + 1]
                rest = content[first_line_end + 1 :]
            new_content = shebang_line + "\n" + self.client_connect_ban_check_block + "\n" + rest.lstrip("\n")
        else:
            new_content = self.client_connect_ban_check_block + "\n" + content.lstrip("\n")

        with open(self.client_connect_script, "w", encoding="utf-8") as f:
            f.write(new_content)
