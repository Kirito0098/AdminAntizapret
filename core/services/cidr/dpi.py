"""DPI log analysis."""
import re

from core.services.cidr.provider_sources import (
    DPI_NODE_CODE_TO_FILE,
    DPI_PROVIDER_ALIASES,
    _normalize_provider_name_token,
)

def _provider_name_to_file(provider_name):
    token = _normalize_provider_name_token(provider_name)
    if not token:
        return None

    if token in DPI_PROVIDER_ALIASES:
        return DPI_PROVIDER_ALIASES[token]

    for alias, file_name in DPI_PROVIDER_ALIASES.items():
        if token.startswith(alias) or alias.startswith(token):
            return file_name
    return None

def _normalize_dpi_severity(value):
    text = str(value or "").strip().lower()
    if not text:
        return "unknown", -1

    if text == "ok" or text.startswith("ok "):
        return "not_detected", 0
    if "not detected" in text:
        return "not_detected", 0
    if "unlikely" in text:
        return "unlikely", 1
    if ("possible" in text or "probably" in text) and "detected" in text:
        return "possible_detected", 2
    if "detected" in text:
        return "detected", 3

    return "unknown", -1

def _dpi_node_id_to_file(node_id):
    cyrillic_homoglyphs = str.maketrans(
        {
            "А": "A",
            "В": "B",
            "С": "C",
            "Е": "E",
            "К": "K",
            "М": "M",
            "Н": "H",
            "О": "O",
            "Р": "P",
            "Т": "T",
            "У": "Y",
            "Х": "X",
        }
    )

    value = str(node_id or "").strip().upper().translate(cyrillic_homoglyphs).lstrip("#")
    if not value:
        return None

    tokens = [item for item in re.split(r"[\.\-_/:\s]+", value) if item]
    for token in tokens:
        file_name = DPI_NODE_CODE_TO_FILE.get(token)
        if file_name:
            return file_name

    if "." in value:
        value = value.split(".", 1)[1]

    code = value.split("-", 1)[0]
    return DPI_NODE_CODE_TO_FILE.get(code)

def analyze_dpi_log(dpi_log_text):
    text = str(dpi_log_text or "")
    if not text.strip():
        return {
            "success": False,
            "message": "Лог DPI пуст",
            "summary": {},
            "nodes": [],
            "providers": [],
            "priority_files": [],
            "critical_files": [],
            "unknown_nodes": [],
        }

    node_pattern = re.compile(r"DPI\s*checking\s*\(\s*#?([^\)]+)\s*\)", re.IGNORECASE)
    status_pattern = re.compile(r"tcp\s*16\s*[-–—]\s*20\s*:\s*([^\n\r]+)", re.IGNORECASE)
    provider_pattern = re.compile(r"provider\s*[:=]\s*([^,\n\r\]]+)", re.IGNORECASE)
    table_row_pattern = re.compile(
        r"^\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*([^\|│]+?)\s*[\|│]\s*$"
    )

    node_events = {}
    unknown_nodes = set()

    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        node_match = node_pattern.search(line)
        table_match = table_row_pattern.match(line)

        node_id = ""
        file_name = None
        status_text = ""

        if node_match:
            node_id = str(node_match.group(1) or "").strip()
            if not node_id:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name:
                provider_match = provider_pattern.search(line)
                provider_name = str(provider_match.group(1) or "").strip() if provider_match else ""
                if provider_name:
                    file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_line = _normalize_provider_name_token(line)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_line:
                        file_name = mapped_file
                        break

            status_match = status_pattern.search(line)
            if not status_match:
                continue

            status_text = str(status_match.group(1) or "").strip()
        elif table_match:
            node_id = str(table_match.group(1) or "").strip()
            provider_name = str(table_match.group(3) or "").strip()
            status_text = str(table_match.group(5) or "").strip()

            node_id_lower = node_id.lower()
            status_lower = status_text.lower()
            if node_id_lower in {"id", "ид"} or status_lower in {"status", "статус"}:
                continue

            if not node_id or not status_text:
                continue

            file_name = _dpi_node_id_to_file(node_id)
            if not file_name and provider_name:
                file_name = _provider_name_to_file(provider_name)

            if not file_name:
                normalized_provider = _normalize_provider_name_token(provider_name)
                for alias, mapped_file in DPI_PROVIDER_ALIASES.items():
                    if alias and alias in normalized_provider:
                        file_name = mapped_file
                        break
        else:
            continue

        severity_key, severity_score = _normalize_dpi_severity(status_text)
        event = node_events.get(node_id)
        if event is None or severity_score > event.get("severity_score", -1):
            node_events[node_id] = {
                "node_id": node_id,
                "file": file_name,
                "severity": severity_key,
                "severity_score": severity_score,
                "status_text": status_text,
            }

        if not file_name:
            unknown_nodes.add(node_id)

    if not node_events:
        return {
            "success": False,
            "message": "В логе не найдены результаты tcp 16-20",
            "summary": {},
            "nodes": [],
            "providers": [],
            "priority_files": [],
            "critical_files": [],
            "unknown_nodes": [],
        }

    provider_stats = {}
    nodes = sorted(node_events.values(), key=lambda item: item["node_id"])
    for item in nodes:
        file_name = item.get("file")
        if not file_name:
            continue

        stats = provider_stats.setdefault(
            file_name,
            {
                "file": file_name,
                "max_severity_score": -1,
                "detected": 0,
                "possible_detected": 0,
                "unlikely": 0,
                "not_detected": 0,
                "nodes": 0,
            },
        )
        stats["nodes"] += 1
        stats[item["severity"]] = stats.get(item["severity"], 0) + 1
        stats["max_severity_score"] = max(stats["max_severity_score"], item["severity_score"])

    providers = sorted(
        provider_stats.values(),
        key=lambda item: (-item["max_severity_score"], -item["nodes"], item["file"]),
    )
    all_seen_files = [item["file"] for item in providers]
    detected_files = [item["file"] for item in providers if item["max_severity_score"] >= 3]
    priority_files = [item["file"] for item in providers if item["max_severity_score"] >= 1]
    critical_files = [item["file"] for item in providers if item["max_severity_score"] >= 2]

    return {
        "success": True,
        "message": "DPI лог обработан",
        "summary": {
            "total_nodes": len(nodes),
            "matched_nodes": sum(1 for item in nodes if item.get("file")),
            "unknown_nodes": len(unknown_nodes),
            "all_seen_files": len(all_seen_files),
            "detected_files": len(detected_files),
            "priority_files": len(priority_files),
            "critical_files": len(critical_files),
        },
        "nodes": nodes,
        "providers": providers,
        "all_seen_files": all_seen_files,
        "detected_files": detected_files,
        "priority_files": priority_files,
        "critical_files": critical_files,
        "unknown_nodes": sorted(unknown_nodes),
    }

