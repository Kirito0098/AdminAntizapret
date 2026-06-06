import os
import subprocess


class ScriptExecutor:
    def __init__(
        self,
        min_cert_expire=1,
        max_cert_expire=3650,
        client_sh_cwd=None,
    ):
        self.min_cert_expire = min_cert_expire
        self.max_cert_expire = max_cert_expire
        self.client_sh_cwd = os.path.abspath(
            client_sh_cwd
            or os.environ.get("APP_BACKUP_AZ_INSTALL_DIR")
            or os.environ.get("ANTIZAPRET_INSTALL_DIR")
            or "/root/antizapret"
        )

    def run_bash_script(self, option, client_name, cert_expire=None):
        if not option.isdigit():
            raise ValueError("Некорректный параметр option")

        # argv-list передаётся в subprocess с shell=False, поэтому shlex.quote()
        # здесь не нужен — кавычки стали бы частью самого аргумента.
        command = ["./client.sh", option, client_name]

        if cert_expire and str(option) == "1":
            if not cert_expire.isdigit() or not (
                self.min_cert_expire <= int(cert_expire) <= self.max_cert_expire
            ):
                raise ValueError("Некорректный срок действия сертификата")
            command.append(cert_expire)

        result = subprocess.run(
            command,
            cwd=self.client_sh_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command, output=result.stdout, stderr=result.stderr
            )
        return result.stdout, result.stderr
