"""Человекочитаемые названия и описания тестов для вкладки «Тесты» в настройках."""

from __future__ import annotations

from tests.test_catalog_data import MODULE_DESCRIPTIONS, MODULE_LABELS, TEST_ENTRIES


def _module_for_nodeid(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def _lookup_entry(nodeid: str) -> dict[str, str] | None:
    if nodeid in TEST_ENTRIES:
        return TEST_ENTRIES[nodeid]
    base = nodeid.split("[", 1)[0]
    if base in TEST_ENTRIES:
        return TEST_ENTRIES[base]
    return None


def _fallback_short_title(nodeid: str) -> str:
    func = nodeid.rsplit("::", 1)[-1]
    if func.startswith("test_"):
        func = func[5:]
    if "[" in func:
        func = func.split("[", 1)[0]
    return func.replace("_", " ").strip().capitalize()


def short_title_for_nodeid(nodeid: str) -> str:
    entry = _lookup_entry(nodeid)
    if entry:
        return entry["title"]
    return _fallback_short_title(nodeid)


def description_for_nodeid(nodeid: str) -> str:
    entry = _lookup_entry(nodeid)
    if entry:
        return entry.get("description", "")
    return ""


def module_label_for_nodeid(nodeid: str) -> str:
    module = _module_for_nodeid(nodeid)
    return MODULE_LABELS.get(
        module,
        module.replace("tests/test_", "").replace("_", " "),
    )


def module_description_for_nodeid(nodeid: str) -> str:
    module = _module_for_nodeid(nodeid)
    return MODULE_DESCRIPTIONS.get(module, "")


def title_for_nodeid(nodeid: str) -> str:
    return f"{module_label_for_nodeid(nodeid)}: {short_title_for_nodeid(nodeid)}"


def enrich_test_nodeids(nodeids: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for nodeid in nodeids:
        module = _module_for_nodeid(nodeid)
        items.append(
            {
                "id": nodeid,
                "title": short_title_for_nodeid(nodeid),
                "description": description_for_nodeid(nodeid),
                "group": MODULE_LABELS.get(module, module),
                "group_description": MODULE_DESCRIPTIONS.get(module, ""),
            }
        )
    return items
