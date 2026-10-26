"""Tests du détail d'une tâche, structuré (#133)."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section, Tag
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


def definitions(html: str) -> dict[str, str]:
    """Termes et définitions de la fiche, texte seul, espaces réduits."""
    match = re.search(r"<dl.*?</dl>", html, re.DOTALL)
    assert match is not None, "pas de <dl>"
    pairs = re.findall(
        r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", match.group(), re.DOTALL
    )
    clean = lambda text: " ".join(re.sub(r"<[^>]+>", " ", text).split())  # noqa: E731
    return {clean(term): clean(value) for term, value in pairs}


class TaskDetailTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")
        self.parent = Todo.objects.create(title="Parent", project=self.project)
        self.task = Todo.objects.create(
            title="Relire",
            project=self.project,
            section=Section.objects.create(project=self.project, name="Réunion"),
            priority="high",
            due_date=date(2025, 11, 24),
            progress=40,
            description="Première ligne\nSeconde ligne",
            parent=self.parent,
        )
        self.task.tags.add(Tag.objects.create(name="urgent"))

    def get(self, todo: Todo) -> str:
        return self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()

    def test_fiche(self):
        fiche = definitions(self.get(self.task))

        self.assertEqual(
            {key: fiche.get(key) for key in ("Projet", "Sujet", "Tags", "Priorité")},
            {
                "Projet": "ASTERICS",
                "Sujet": "Réunion",
                "Tags": "urgent",
                "Priorité": "Haute",
            },
        )
        self.assertEqual(fiche["Échéance"], "24 novembre 2025")
        self.assertEqual(fiche["Avancement"], "40 % · en cours")
        self.assertEqual(fiche["Tâche parente"], "Parent")
        self.assertIn("Créée le", fiche)

    def test_pastille_du_projet_et_lien_vers_le_parent(self):
        html = self.get(self.task)

        self.assertIn("bg-teal-500", html)
        self.assertIn(
            f'href="{reverse("todolist:todo_detail", args=[self.parent.pk])}"', html
        )

    def test_valeurs_absentes(self):
        task = Todo.objects.create(title="Nue", project=self.project)

        fiche = definitions(self.get(task))

        self.assertEqual(fiche["Sujet"], "Aucun")
        self.assertEqual(fiche["Échéance"], "Aucune")
        self.assertNotIn("Tags", fiche)
        self.assertNotIn("Tâche parente", fiche)

    def test_avancement_d_un_parent(self):
        self.task.progress = 100
        self.task.save()

        fiche = definitions(self.get(self.parent))

        self.assertEqual(
            fiche["Avancement"], "100 % · à valider (calculé à partir des sous-tâches)"
        )

    def test_description_avec_ses_retours_a_la_ligne(self):
        html = self.get(self.task)

        self.assertIn('<h2 id="description-title"', html)
        self.assertIn("Première ligne<br>Seconde ligne", html)

    def test_section_des_sous_taches_avec_son_bouton(self):
        html = self.get(self.parent)

        section = re.search(
            r'<section aria-labelledby="children-title".*?</section>', html, re.DOTALL
        )
        assert section is not None
        self.assertIn("Relire", section.group())
        self.assertIn(
            reverse("todolist:todo_create") + f"?parent={self.parent.pk}",
            section.group(),
        )

    def test_section_des_sous_taches_vide(self):
        html = self.get(self.task)

        self.assertIn("Aucune sous-tâche.", html)

    def test_note_d_origine(self):
        note = Note.objects.create(
            date="2025-11-24", body="# P\n## S\n### TODO\n- De la note"
        )
        process_note_parts(note)
        task = Todo.objects.get(title="De la note")

        html = self.get(task)

        self.assertEqual(
            definitions(html)["Note d'origine"], "Note du lundi 24 novembre 2025"
        )
        self.assertIn(
            f'href="{reverse("note_taking:note_detail", args=[note.pk])}"', html
        )
