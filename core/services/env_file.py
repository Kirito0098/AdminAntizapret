import os


class EnvFileService:
    def __init__(self, env_file_path):
        self.env_file_path = env_file_path

    def set_env_value(self, key, value):
        """Update or append env key in local .env file."""
        env_path = self.env_file_path
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def get_env_value(self, key, default=""):
        """Reads env value from .env first, then from process env as fallback."""
        env_path = self.env_file_path
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip()
        return os.getenv(key, default)
