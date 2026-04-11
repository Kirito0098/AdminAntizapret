import os
import re
import socket
import time


class OpenVPNSocketReaderService:
    def __init__(
        self,
        *,
        openvpn_socket_dir,
        openvpn_socket_timeout,
        openvpn_socket_idle_timeout,
        openvpn_log_tail_lines,
        openvpn_event_max_response_bytes,
    ):
        self.openvpn_socket_dir = openvpn_socket_dir
        self.openvpn_socket_timeout = openvpn_socket_timeout
        self.openvpn_socket_idle_timeout = openvpn_socket_idle_timeout
        self.openvpn_log_tail_lines = openvpn_log_tail_lines
        self.openvpn_event_max_response_bytes = openvpn_event_max_response_bytes

    def read_log_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except FileNotFoundError:
            return ""
        except Exception:
            return ""

    def openvpn_socket_path(self, profile_key):
        return os.path.join(self.openvpn_socket_dir, f"{profile_key}.sock")

    def query_openvpn_management_socket(self, socket_path, command, max_response_bytes=0):
        if not socket_path or not os.path.exists(socket_path):
            return ""

        cmd = (command or "").strip()
        if not cmd:
            return ""

        max_response_bytes = int(max_response_bytes or 0)
        received_bytes = 0

        def _append_chunk(raw_bytes, target):
            nonlocal received_bytes
            if not raw_bytes:
                return False

            if max_response_bytes > 0:
                remaining = max_response_bytes - received_bytes
                if remaining <= 0:
                    return True
                if len(raw_bytes) > remaining:
                    raw_bytes = raw_bytes[:remaining]
                    target.append(raw_bytes.decode("utf-8", errors="ignore"))
                    received_bytes += len(raw_bytes)
                    return True

            target.append(raw_bytes.decode("utf-8", errors="ignore"))
            received_bytes += len(raw_bytes)
            return False

        chunks = []
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock_conn:
                sock_conn.settimeout(self.openvpn_socket_timeout)
                sock_conn.connect(socket_path)

                try:
                    banner = sock_conn.recv(65536)
                    if banner:
                        if _append_chunk(banner, chunks):
                            return "".join(chunks)
                except socket.timeout:
                    pass

                sock_conn.sendall((cmd + "\n").encode("utf-8", errors="ignore"))

                idle_timeout = self.openvpn_socket_idle_timeout
                is_status_cmd = cmd.lower().startswith("status")
                read_deadline = time.monotonic() + (1.4 if is_status_cmd else 0.9)
                got_payload = False
                timeout_streak = 0
                end_probe = ""

                while time.monotonic() < read_deadline:
                    try:
                        sock_conn.settimeout(idle_timeout)
                        data = sock_conn.recv(65536)
                    except socket.timeout:
                        timeout_streak += 1
                        if got_payload and timeout_streak >= 2:
                            break
                        continue
                    if not data:
                        break
                    hit_limit = _append_chunk(data, chunks)
                    text_chunk = chunks[-1] if chunks else ""
                    got_payload = True
                    timeout_streak = 0
                    if is_status_cmd:
                        end_probe = (end_probe + text_chunk)[-256:]
                        if re.search(r"(^|\n)END(\n|$)", end_probe):
                            break
                    if hit_limit:
                        break

                try:
                    sock_conn.sendall(b"quit\n")
                except Exception:
                    pass

                try:
                    sock_conn.settimeout(0.05)
                    while True:
                        tail = sock_conn.recv(65536)
                        if not tail:
                            break
                        if _append_chunk(tail, chunks):
                            break
                except Exception:
                    pass
        except Exception:
            return ""

        return "".join(chunks)

    def extract_status_payload_from_management(self, raw):
        lines = []
        for raw_line in (raw or "").splitlines():
            line = raw_line.strip("\r")
            if not line:
                continue
            if (
                line.startswith("TITLE,")
                or line.startswith("TIME,")
                or line.startswith("HEADER,")
                or line.startswith("TITLE\t")
                or line.startswith("TIME\t")
                or line.startswith("HEADER\t")
                or line.startswith("TITLE ")
                or line.startswith("TIME ")
                or line.startswith("HEADER ")
            ):
                lines.append(line)
                continue
            if (
                line.startswith("CLIENT_LIST,")
                or line.startswith("ROUTING_TABLE,")
                or line.startswith("GLOBAL_STATS,")
                or line.startswith("CLIENT_LIST\t")
                or line.startswith("ROUTING_TABLE\t")
                or line.startswith("GLOBAL_STATS\t")
                or line.startswith("CLIENT_LIST ")
                or line.startswith("ROUTING_TABLE ")
                or line.startswith("GLOBAL_STATS ")
            ):
                lines.append(line)
                continue
            if line == "END":
                lines.append(line)

        return "\n".join(lines)

    def extract_event_payload_from_management(self, raw):
        lines = []
        for raw_line in (raw or "").splitlines():
            line = raw_line.strip("\r")
            if not line:
                continue

            if line.startswith(">LOG:"):
                parts = line.split(",", 2)
                msg = parts[2] if len(parts) >= 3 else ""
                msg = msg.strip()
                if msg:
                    lines.append(msg)
                continue

            if any(token in line for token in ("Peer Connection Initiated", "VERIFY OK", "peer info:")):
                lines.append(line)

        return "\n".join(lines)

    def read_status_source(self, profile_key, fallback_path):
        _ = fallback_path
        socket_path = self.openvpn_socket_path(profile_key)
        raw_mgmt = self.query_openvpn_management_socket(socket_path, "status 3")
        payload = self.extract_status_payload_from_management(raw_mgmt)
        if payload:
            return {
                "raw": payload,
                "source_name": os.path.basename(socket_path),
                "exists": True,
                "updated_at_ts": int(time.time()),
                "source_type": "socket",
            }

        return {
            "raw": "",
            "source_name": os.path.basename(socket_path),
            "exists": False,
            "updated_at_ts": 0,
            "source_type": "socket",
        }

    def read_event_source(self, profile_key, fallback_path):
        _ = fallback_path
        socket_path = self.openvpn_socket_path(profile_key)
        log_cmd = "log all" if self.openvpn_log_tail_lines == 0 else f"log {self.openvpn_log_tail_lines}"
        raw_mgmt = self.query_openvpn_management_socket(
            socket_path,
            log_cmd,
            max_response_bytes=self.openvpn_event_max_response_bytes,
        )
        payload = self.extract_event_payload_from_management(raw_mgmt)
        if payload:
            return {
                "raw": payload,
                "source_name": os.path.basename(socket_path),
                "exists": True,
                "updated_at_ts": int(time.time()),
                "source_type": "socket",
            }

        return {
            "raw": "",
            "source_name": os.path.basename(socket_path),
            "exists": False,
            "updated_at_ts": 0,
            "source_type": "socket",
        }
