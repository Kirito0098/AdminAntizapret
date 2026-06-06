"""Проверка, что все Jinja2-шаблоны панели компилируются без ошибок."""

import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_ROOTS = (
    PROJECT_ROOT / "templates",
    PROJECT_ROOT / "tg_mini" / "templates",
    PROJECT_ROOT / "ip_blocked" / "templates",
)


def _build_template_env(loader_root: Path) -> Environment:
    """Окружение Jinja2 с заглушками globals, как в test_feature_toggles.py."""
    env = Environment(
        loader=FileSystemLoader(str(loader_root)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals.update(
        {
            "url_for": lambda endpoint, **kwargs: f"/{endpoint}",
            "csrf_token": lambda: "test-token",
            "csp_nonce": "test-nonce",
            "current_user": None,
            "feature_modules": {},
            "panel_branding": {"name": "AdminAntizapret", "version": "test"},
        }
    )
    return env


def _iter_template_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.html") if path.is_file())


class JinjaTemplatesCompileTests(unittest.TestCase):
    def test_all_template_roots_have_html_files(self):
        for root in TEMPLATE_ROOTS:
            with self.subTest(root=str(root)):
                self.assertTrue(root.is_dir(), msg=f"missing template root: {root}")
                self.assertGreater(len(_iter_template_files(root)), 0)

    def test_all_templates_compile(self):
        failures: list[str] = []
        compiled = 0

        for root in TEMPLATE_ROOTS:
            env = _build_template_env(root)
            for template_path in _iter_template_files(root):
                template_name = template_path.relative_to(root).as_posix()
                with self.subTest(root=str(root), template=template_name):
                    try:
                        env.get_template(template_name)
                        compiled += 1
                    except Exception as exc:
                        failures.append(f"{template_path}: {exc}")

        self.assertFalse(
            failures,
            msg="Jinja compile failures:\n" + "\n".join(failures),
        )
        self.assertGreater(compiled, 0)


if __name__ == "__main__":
    unittest.main()
