"""Tests des titres d'onglet et du vocabulaire (#130).

Titre : « Page · Section », la section (Notes, Tâches) ajoutée par le gabarit de
base de l'application. Vocabulaire : « tâche », pas « TODO ».
"""

import re

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from images.models import Image
from note_taking.models import Note, NotePart
from todolist.forms import TodoForm
from todolist.models import Todo

TITLE_REGEX = re.compile(r"<title>(?P<title>.*?)</title>", re.DOTALL)
TAG_REGEX = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.DOTALL)


LABEL_ATTR_REGEX = re.compile(r'(?:aria-label|title|data-confirm)="(?P<value>[^"]*)"')


def visible_text(html: str) -> str:
    """Texte lu par l'utilisateur : contenu affiché et libellés des attributs."""
    labels = " ".join(LABEL_ATTR_REGEX.findall(html))
    return TAG_REGEX.sub(" ", html) + " " + labels


class PageTitlesTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        NotePart.objects.create(
            note=self.note, project=Project.objects.create(name="P"), content="x"
        )
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        self.todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="Relire"
        )

    def pages(self) -> dict[str, str]:
        note, todo = self.note.pk, self.todo.pk
        return {
            "/": "Gestion générale",
            reverse("note_taking:index"): "Gestion des notes",
            reverse("note_taking:notes_list"): "Liste des notes · Notes",
            reverse("note_taking:note_detail", args=[note]): (
                "Note du 24 novembre 2025 · Notes"
            ),
            reverse("note_taking:note_md", args=[note]): (
                "Note du 24 novembre 2025 en Markdown · Notes"
            ),
            reverse("note_taking:new_note"): "Nouvelle note · Notes",
            reverse("note_taking:edit_note", args=[note]): (
                "Modifier la note du 24 novembre 2025 · Notes"
            ),
            reverse("note_taking:notes_search"): "Recherche de notes · Notes",
            reverse("note_taking:images_list"): "Liste des images · Notes",
            reverse("note_taking:image_detail", args=[self.image.pk]): (
                "Image banc.png · Notes"
            ),
            reverse("todolist:index"): "Gestion des tâches",
            reverse("todolist:todo_list"): "Liste des tâches · Tâches",
            reverse("todolist:todo_detail", args=[todo]): "Tâche « Relire » · Tâches",
            reverse("todolist:todo_create"): "Nouvelle tâche · Tâches",
            reverse("todolist:todo_edit", args=[todo]): (
                "Modifier la tâche « Relire » · Tâches"
            ),
        }

    def titles(self, url: str) -> list[str]:
        html = self.client.get(url).content.decode()
        return [t.strip() for t in TITLE_REGEX.findall(html)]

    def test_titre_de_chaque_page(self):
        for url, title in self.pages().items():
            with self.subTest(url=url):
                self.assertEqual(self.titles(url), [title])

    def test_titres_tous_differents(self):
        titles = [tuple(self.titles(url)) for url in self.pages()]

        self.assertEqual(len(titles), len(set(titles)))

    def test_compte_rendu_d_import(self):
        response = self.client.post(
            reverse("note_taking:import_files"),
            {"import_files": [self.qmd_file()]},
        )

        self.assertEqual(
            TITLE_REGEX.findall(response.content.decode()),
            ["Compte rendu d'import · Notes"],
        )

    def qmd_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile("2025-12-01.qmd", b"# P\nx\n")


class VocabularyTests(TestCase):
    def test_tache_et_pas_todo_dans_les_pages(self):
        todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0], title="Relire"
        )
        urls = [
            "/",
            reverse("todolist:index"),
            reverse("todolist:todo_list"),
            reverse("todolist:todo_detail", args=[todo.pk]),
            reverse("todolist:todo_create"),
            reverse("todolist:todo_edit", args=[todo.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                text = visible_text(self.client.get(url).content.decode())
                self.assertNotRegex(text, r"\b(?:TODO|Todos?)\b")

    def test_libelles_du_formulaire_en_francais(self):
        labels = {name: str(field.label) for name, field in TodoForm().fields.items()}

        self.assertEqual(
            labels,
            {
                "title": "Titre",
                "description": "Description",
                "progress": "Avancement (%)",
                "priority": "Priorité",
                "due_date": "Échéance",
                "project": "Projet",
                "section_path": "Chemin",
                "tags": "Tags",
                "parent": "Tâche parente",
            },
        )
