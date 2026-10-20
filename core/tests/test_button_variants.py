"""Tests des variantes de bouton : forme commune, survol, usage (#145)."""

import re

from django.test import TestCase
from django.urls import reverse

from core.templatetags.ui import BUTTON_VARIANTS
from images.models import Image
from todolist.models import Todo

SHAPE = "inline-flex items-center gap-2 rounded-xl p-2 font-semibold"


def classes(variant: str) -> list[str]:
    return BUTTON_VARIANTS[variant].split()


class ButtonVariantsTests(TestCase):
    def test_forme_commune_a_toutes_les_variantes(self):
        for variant in BUTTON_VARIANTS:
            with self.subTest(variant=variant):
                self.assertTrue(BUTTON_VARIANTS[variant].startswith(SHAPE + " "))

    def test_boutons_pleins_eclaircis_au_survol(self):
        for variant, color in (("primary", "blue"), ("danger", "red")):
            with self.subTest(variant=variant):
                self.assertIn(f"bg-{color}-100", classes(variant))
                self.assertIn(f"hover:bg-{color}-50", classes(variant))

    def test_ghost_prend_un_fond_au_survol(self):
        self.assertIn("hover:bg-slate-200", classes("ghost"))
        self.assertIn("hover:bg-red-100", classes("ghost-danger"))
        for variant in ("ghost", "ghost-danger"):
            with self.subTest(variant=variant):
                self.assertFalse([c for c in classes(variant) if c.startswith("bg-")])

    def test_suppressions_en_texte_rouge(self):
        for variant in ("danger", "ghost-danger"):
            with self.subTest(variant=variant):
                self.assertIn("text-red-800", classes(variant))


def header(html: str) -> str:
    match = re.search(r"<header.*?</header>", html, re.DOTALL)
    assert match is not None
    return match.group()


class ButtonUsageTests(TestCase):
    """Actions sur l'objet affiché : barre d'outils ghost à côté du titre."""

    def test_suppression_d_une_image_en_ghost_danger(self):
        image = Image.objects.create(name="banc.png", file="note_images/banc.png")

        html = self.client.get(
            reverse("note_taking:image_detail", args=[image.pk])
        ).content.decode()

        self.assertIn(BUTTON_VARIANTS["ghost-danger"], header(html))
        self.assertRegex(header(html), r"Supprimer l(&#x27;|')image")

    def test_barre_d_outils_d_une_todo(self):
        todo = Todo.objects.create(title="T")

        html = self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()

        toolbar = header(html)
        self.assertIn("<h1", toolbar)
        self.assertIn(
            f'<a class="{BUTTON_VARIANTS["ghost"]}"'
            f' href="{reverse("todolist:todo_edit", args=[todo.pk])}"',
            toolbar,
        )
        self.assertIn(
            f'<a class="{BUTTON_VARIANTS["ghost-danger"]}"'
            f' href="{reverse("todolist:todo_delete", args=[todo.pk])}"',
            toolbar,
        )
