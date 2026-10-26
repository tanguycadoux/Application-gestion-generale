"""Sens des dépendances entre apps (#179) : core en base, sans cycle."""

import ast
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

APPS = ("core", "images", "note_taking", "todolist")

# Une app ne dépend que de celles qui sont en dessous d'elle.
ALLOWED = {
    "core": set(),
    "images": {"core"},
    "note_taking": {"core", "images"},
    "todolist": {"core", "note_taking"},
}

# Nom d'URL d'une autre app dans un gabarit : {% url "app:nom" %}, {% nav_link "app:nom" … %}.
URL_NAME_REGEX = re.compile(r"""["'](?P<app>\w+):\w+["']""")


def source_files(app: str, pattern: str):
    """Fichiers de l'app, hors tests et migrations."""
    root = Path(settings.BASE_DIR) / app
    for path in root.rglob(pattern):
        parts = path.relative_to(root).parts
        if "tests" not in parts and "migrations" not in parts:
            yield path


def imported_apps(app: str) -> set[str]:
    """Apps du projet importées par le code Python de `app`."""
    found: set[str] = set()
    for path in source_files(app, "*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            found.update(name.split(".")[0] for name in names)
    return (found & set(APPS)) - {app}


def template_apps(app: str) -> set[str]:
    """Apps dont les gabarits de `app` citent une URL."""
    found: set[str] = set()
    for path in source_files(app, "*.html"):
        found.update(URL_NAME_REGEX.findall(path.read_text(encoding="utf-8")))
    return (found & set(APPS)) - {app}


class DependencyTests(TestCase):
    def test_imports_dans_le_sens_prevu(self):
        for app in APPS:
            with self.subTest(app=app):
                self.assertLessEqual(imported_apps(app), ALLOWED[app])

    def test_gabarits_dans_le_sens_prevu(self):
        for app in APPS:
            with self.subTest(app=app):
                self.assertLessEqual(template_apps(app), ALLOWED[app])

    def test_sens_prevu_sans_cycle(self):
        """Le graphe autorisé lui-même est sans cycle."""
        visited: set[str] = set()

        def visit(app: str, path: tuple[str, ...]):
            self.assertNotIn(app, path, f"cycle : {' → '.join((*path, app))}")
            if app not in visited:
                for dependency in ALLOWED[app]:
                    visit(dependency, (*path, app))
                visited.add(app)

        for app in APPS:
            visit(app, ())
