"""Tests des titres de page : taille de base et hiérarchie (#118)."""

import re

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from images.models import Image
from note_taking.models import Note, NotePart
from todolist.models import Todo

from .stylesheets import read_source_css

HEADING_REGEX = re.compile(r"<h([1-6])[\s>]")


def main_headings(html: str) -> list[int]:
    """Niveaux des titres du contenu principal (<main>), dans l'ordre."""
    main = html[html.index("<main") : html.index("</main>")]
    return [int(level) for level in HEADING_REGEX.findall(main)]


class HeadingStylesTests(TestCase):
    def test_styles_de_base_des_titres(self):
        css = read_source_css()

        self.assertIn("h1 {\n        @apply text-2xl font-semibold;", css)
        self.assertIn("h2 {\n        @apply text-xl font-semibold;", css)
        self.assertIn("h3 {\n        @apply text-lg font-semibold;", css)


class HeadingHierarchyTests(TestCase):
    """Un seul h1 par page, en premier, et des niveaux qui ne sautent pas."""

    def setUp(self):
        project = Project.objects.create(name="P")
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        section = self.section = Section.objects.create(project=project, name="S")
        NotePart.objects.create(
            note=self.note, project=project, section=section, content="x"
        )
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        self.todo = Todo.objects.create(title="T", project=project)

    def pages(self) -> list[str]:
        return [
            "/",
            reverse("note_taking:index"),
            reverse("note_taking:notes_list"),
            reverse("note_taking:note_detail", args=[self.note.date]),
            reverse("note_taking:note_md", args=[self.note.date]),
            reverse("note_taking:new_note"),
            reverse("note_taking:edit_note", args=[self.note.date]),
            reverse("note_taking:notes_search"),
            reverse("note_taking:images_list"),
            reverse("note_taking:image_detail", args=[self.image.pk]),
            reverse("todolist:index"),
            reverse("todolist:todo_list"),
            reverse("todolist:todo_detail", args=[self.todo.pk]),
            reverse("todolist:todo_create"),
        ]

    def assertHierarchy(self, html: str) -> None:
        levels = main_headings(html)
        self.assertEqual(levels[:1], [1])
        self.assertEqual(levels.count(1), 1)
        for previous, level in zip(levels, levels[1:], strict=False):
            self.assertLessEqual(level, previous + 1, levels)

    def test_hierarchie_des_pages(self):
        for url in self.pages():
            with self.subTest(url=url):
                self.assertHierarchy(self.client.get(url).content.decode())

    def test_hierarchie_des_resultats_de_recherche(self):
        url = reverse("note_taking:notes_search")
        page = self.client.get(url).content.decode()
        results = self.client.post(
            url, {"subjects": [str(self.section.pk)]}, HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("<h", results)

        # Les résultats s'insèrent sous le h1 de la page de recherche.
        self.assertHierarchy(page.replace("</main>", results + "</main>"))
