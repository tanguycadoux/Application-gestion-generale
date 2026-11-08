"""Vocabulaire de l'interface : « passage », jamais « note part » (#362).

`NotePart` reste le nom du modèle dans le code (#387 le renommera) ; l'utilisateur,
lui, ne lit que « passage ». Ces tests empêchent le mot de revenir dans ce qui
s'affiche : pages rendues, messages, gabarits et chaînes du code Python.
"""

import ast
import re
from pathlib import Path

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

BASE_DIR = Path(settings.BASE_DIR)
APPS = ("core", "images", "note_taking", "todolist", "app_gestion")

# « note part », « note parts », « Note-part », « notepart » : tout ce qu'un
# utilisateur pourrait lire. Pas les identifiants (`note_part`, `NotePart`).
FORBIDDEN = re.compile(r"\bnote[\s-]?parts?\b", re.IGNORECASE)

# Commentaires des gabarits : ils ne sont jamais rendus.
TEMPLATE_COMMENTS = re.compile(
    r"\{#.*?#\}|\{% comment %\}.*?\{% endcomment %\}", re.DOTALL
)

NOTE_BODY = """# Alpha
## Réunion
banc thermique
### Suite
::: {.metadata}
tags: [suivi]
:::
- [ ] Relancer le banc
"""


class VisiblePagesTests(TestCase):
    """Les pages que l'utilisateur voit, avec des données qui affichent compteurs,
    résultats, arbre des chemins, aide et messages."""

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=NOTE_BODY)
        process_note_parts(self.note)
        self.project = Project.objects.get(name="Alpha")
        self.section = Section.objects.get(project=self.project, name="Réunion")

    def assert_no_note_part(self, text: str) -> None:
        self.assertEqual(FORBIDDEN.findall(text), [])

    def pages(self) -> dict[str, str]:
        search = reverse("note_taking:notes_search")
        rename = reverse("core:section_rename", args=[self.project.pk, self.section.pk])
        task = Todo.objects.get(title="Relancer le banc")
        return {
            "projets": reverse("core:projects"),
            "chemins": reverse("core:project_paths", args=[self.project.pk]),
            "chemin_bilan": f"{rename}?name=Rencontre",
            "recherche": search,
            "recherche_resultats": f"{search}?q=banc",
            "recherche_document": f"{search}?q=banc&view=document&group=path",
            "recherche_filtres": f"{search}?projects={self.project.pk}",
            "recherche_aucun": f"{search}?q=introuvable",
            "note": reverse("note_taking:note_detail", args=[self.note.date]),
            "taches_bilan": reverse("todolist:note_review", args=[self.note.date]),
            "taches_liste": reverse("todolist:todo_list"),
            "tache": reverse("todolist:todo_detail", args=[task.pk]),
        }

    def test_pages_sans_note_part(self):
        for name, url in self.pages().items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assert_no_note_part(response.content.decode())

    def test_resultats_htmx_sans_note_part(self):
        response = self.client.get(
            reverse("note_taking:notes_search"),
            {"q": "banc"},
            headers={"HX-Request": "true"},
        )

        self.assert_no_note_part(response.content.decode())

    def test_message_de_suppression_d_un_niveau_utilise(self):
        url = reverse("core:section_delete", args=[self.project.pk, self.section.pk])

        response = self.client.post(url, follow=True)

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        texts.append(response.content.decode())
        for text in texts:
            self.assert_no_note_part(text)
        self.assertContains(response, "passage")

    def test_compte_rendu_d_import(self):
        upload = SimpleUploadedFile(
            "2025-11-25.qmd",
            b"---\ndate: 2025-11-25\n---\n# Alpha\n## Suite\n- [ ] T\n",
        )

        response = self.client.post(
            reverse("note_taking:import_files"), {"import_files": [upload]}
        )

        self.assertEqual(response.status_code, 200)
        self.assert_no_note_part(response.content.decode())


class SourcesTests(TestCase):
    """Ce qui peut s'afficher, lu dans les sources : un nouveau gabarit ou un
    nouveau message échoue ici avant d'arriver dans une page."""

    def test_gabarits_sans_note_part(self):
        """Hors commentaires et hors pages de debug (#235), qui montrent le JSON
        de l'analyse tel quel."""
        for app in APPS:
            for path in (BASE_DIR / app).glob("**/templates/**/*.html"):
                if path.name.startswith("debug_"):
                    continue
                with self.subTest(path=str(path.relative_to(BASE_DIR))):
                    text = TEMPLATE_COMMENTS.sub("", path.read_text(encoding="utf-8"))
                    self.assertEqual(FORBIDDEN.findall(text), [])

    def test_scripts_sans_note_part(self):
        for app in APPS:
            for path in (BASE_DIR / app).glob("**/static/**/*.js"):
                with self.subTest(path=str(path.relative_to(BASE_DIR))):
                    text = path.read_text(encoding="utf-8")
                    self.assertEqual(FORBIDDEN.findall(text), [])

    def test_chaines_python_sans_note_part(self):
        """Libellés, messages, aide des commandes : toute chaîne du code, sauf les
        docstrings, qui parlent du modèle aux développeurs. Les tests et les
        migrations ne s'affichent pas."""
        for app in APPS:
            for path in (BASE_DIR / app).glob("**/*.py"):
                parts = path.relative_to(BASE_DIR).parts
                if "tests" in parts or "migrations" in parts:
                    continue
                with self.subTest(path=str(path.relative_to(BASE_DIR))):
                    self.assertEqual(user_strings_with_note_part(path), [])


def user_strings_with_note_part(path: Path) -> list[str]:
    """Les chaînes d'un module, hors docstrings, qui contiennent le mot."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        f"ligne {node.lineno} : {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and FORBIDDEN.search(node.value)
    ]
