"""Tests des titres de page : taille de base et hiérarchie (#118)."""

import re
import unittest

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Subject
from images.models import Image
from note_taking.models import Note, NotePart
from todolist.models import Todo

HEADING_REGEX = re.compile(r"<h([1-6])[\s>]")


def main_headings(html: str) -> list[int]:
    """Niveaux des titres du contenu principal (<main>), dans l'ordre."""
    main = html[html.index("<main") : html.index("</main>")]
    return [int(level) for level in HEADING_REGEX.findall(main)]


class HeadingStylesTests(TestCase):
    @unittest.expectedFailure
    def test_styles_de_base_des_titres(self):
        html = self.client.get("/").content.decode()

        self.assertIn("h1 {\n                @apply text-2xl font-semibold;", html)
        self.assertIn("h2 {\n                @apply text-xl font-semibold;", html)
        self.assertIn("h3 {\n                @apply text-lg font-semibold;", html)

    @unittest.expectedFailure
    def test_classes_de_taille_redondantes_retirees(self):
        image = Image.objects.create(name="banc.png", file="note_images/banc.png")

        html = self.client.get(
            reverse("note_taking:image_detail", args=[image.pk])
        ).content.decode()

        self.assertNotRegex(html, r"<h[12][^>]*text-(2xl|xl)")


class HeadingHierarchyTests(TestCase):
    """Un seul h1 par page, en premier, et des niveaux qui ne sautent pas."""

    def setUp(self):
        project = Project.objects.create(name="P")
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        subject = Subject.objects.create(name="S")
        NotePart.objects.create(
            note=self.note, project=project, subject=subject, content="x"
        )
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        self.todo = Todo.objects.create(title="T", project=project)

    def pages(self) -> list[str]:
        return [
            "/",
            reverse("note_taking:index"),
            reverse("note_taking:notes_list"),
            reverse("note_taking:note_detail", args=[self.note.pk]),
            reverse("note_taking:note_md", args=[self.note.pk]),
            reverse("note_taking:new_note"),
            reverse("note_taking:edit_note", args=[self.note.pk]),
            reverse("note_taking:notes_search"),
            reverse("note_taking:images_list"),
            reverse("note_taking:image_detail", args=[self.image.pk]),
            reverse("todolist:index"),
            reverse("todolist:todo_list"),
            reverse("todolist:todo_detail", args=[self.todo.pk]),
            reverse("todolist:todo_create"),
            reverse("todolist:todo_delete", args=[self.todo.pk]),
        ]

    def assertHierarchy(self, html: str) -> None:
        levels = main_headings(html)
        self.assertEqual(levels[:1], [1])
        self.assertEqual(levels.count(1), 1)
        for previous, level in zip(levels, levels[1:], strict=False):
            self.assertLessEqual(level, previous + 1, levels)

    @unittest.expectedFailure
    def test_hierarchie_des_pages(self):
        for url in self.pages():
            with self.subTest(url=url):
                self.assertHierarchy(self.client.get(url).content.decode())

    @unittest.expectedFailure
    def test_hierarchie_des_resultats_de_recherche(self):
        url = reverse("note_taking:notes_search")
        page = self.client.get(url).content.decode()
        results = self.client.post(
            url, {"subjects": ["S"]}, HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("<h", results)

        # Les résultats s'insèrent sous le h1 de la page de recherche.
        self.assertHierarchy(page.replace("</main>", results + "</main>"))
