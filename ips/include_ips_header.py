import os

INCLUDE_IPS_FILE = "/root/antizapret/config/include-ips.txt"

default_header = """# Добавление IPv4-адресов для маршрутизации через AntiZapret VPN
#
# Формат записи: A.B.C.D/M
# Где:
#   A.B.C.D - IPv4-адрес
#   M       - размер маски подсети (1-32)
#
# Примеры записи:
#   5.255.255.242/32  - добавление одного IPv4-адреса
#   66.22.192.0/18    - добавление подсети с маской 18 (16382 IPv4-адреса)
#   104.24.0.0/14     - добавление подсети с маской 14 (262142 IPv4-адреса)
#   34.3.3.0/24       - добавление подсети с маской 24 (254 IPv4-адреса)
#
# Строки начинающиеся с # это комментарии и они не обрабатываются
#
"""

def load_header():
    return default_header


def get_existing_comments(path):
    if not os.path.exists(path):
        return []
    header = load_header()
    header_lines = header.rstrip().split('\n')
    try:
        with open(path, 'r') as f:
            lines = [line.rstrip() for line in f]
    except FileNotFoundError:
        return []
    # Check if header matches
    if len(lines) < len(header_lines):
        return []
    for i, h_line in enumerate(header_lines):
        if lines[i] != h_line:
            return []
    # Collect comments after header
    comments = []
    for line in lines[len(header_lines):]:
        if line.startswith('#'):
            comments.append(line[1:].strip())  # remove # and strip
        elif line.strip() == '':
            continue
        else:
            # IPs start, stop
            break
    return comments


def write_include_ips_file(path, ips, comments=None):
    if comments is None:
        comments = []
    elif isinstance(comments, str):
        comments = [comments]
    header = load_header()
    existing_comments = get_existing_comments(path)
    all_comments = existing_comments + comments
    # Keep only the last 5 comments
    all_comments = all_comments[-5:]
    with open(path, "w") as f:
        f.write(header)
        for c in all_comments:
            f.write(f"# {c}\n")
        for ip in sorted(ips):
            f.write(f"{ip}\n")
