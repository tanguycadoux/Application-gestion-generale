"""Bloc « À traiter » de l'accueil général (#384) : ce qu'on a noté vite revient
tant qu'on ne s'en est pas occupé.

Quatre rubriques : tâches à revoir (par note, vers le bilan), tâches en cours sans
échéance (les plus anciennes d'abord, vers la liste filtrée), texte sans projet
(vers chaque note et la recherche filtrée), tâches sans projet hors bilan.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, Passage
from todolist.models import Task

INDEX = reverse("core:index")


class PendingBlockTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")

    def task(self, title, **fields):
        fields.setdefault("project", self.project)
        return Task.objects.create(title=title, **fields)

    def to_review(self, title, note, **fields):
        return self.task(
            title,
            created_from_note=True,
            note_date=note.date,
            note_line_text=title,
            note_state=Task.NoteState.TO_REVIEW,
            **fields,
        )

    def html(self):
        return self.client.get(INDEX).content.decode()

    def test_bloc_a_cote_des_autres(self):
        html = self.html()

        self.assertIn(">À traiter</h2>", html)
        self.assertLess(
            html.index(">Tâches à échéance proche</h2>"), html.index(">À traiter</h2>")
        )

    def test_rien_a_traiter(self):
        self.task("Datée", due_date=date(2030, 1, 1))

        self.assertIn("Rien à traiter.", self.html())

    def test_taches_a_revoir_par_note_vers_le_bilan(self):
        old = Note.objects.create(date="2026-11-02")
        new = Note.objects.create(date="2026-11-20")
        self.to_review("Une", new)
        self.to_review("Deux", new, project=None)
        self.to_review("Trois", old)
        self.task("Revue", note_state=Task.NoteState.REVIEWED, due_date=date.today())

        response = self.client.get(INDEX)
        html = response.content.decode()

        self.assertIn("Tâches à revoir", html)
        for note in (old, new):
            self.assertIn(
                f'href="{reverse("todolist:note_review", args=[note.date])}"', html
            )
        self.assertIn("2 tâches, dont 1 sans projet", html)
        # La note qui attend depuis le plus longtemps d'abord.
        self.assertLess(
            html.index(reverse("todolist:note_review", args=[old.date])),
            html.index(reverse("todolist:note_review", args=[new.date])),
        )
        self.assertNotIn("Revue", html)

    def test_sans_echeance_les_plus_anciennes_d_abord(self):
        first = self.task("Ancienne")
        second = self.task("Récente")
        Task.objects.filter(pk=first.pk).update(
            created_at=second.created_at - timedelta(days=3)
        )

        html = self.html()

        self.assertIn("Tâches en cours sans échéance", html)
        self.assertLess(html.index("Ancienne"), html.index("Récente"))
        self.assertIn(f'href="{reverse("todolist:task_list")}?due=none"', html)

    def test_sans_echeance_ni_terminees_ni_voulues_ni_a_revoir(self):
        note = Note.objects.create(date="2026-11-02")
        self.task("Faite", done=True, progress=100)
        self.task("Voulue", no_due_date=True)
        self.task("Datée", due_date=date(2030, 1, 1))
        self.to_review("Au bilan", note)

        html = self.html()

        self.assertNotIn("Tâches en cours sans échéance", html)
        for title in ("Faite", "Voulue", "Datée", "Au bilan"):
            with self.subTest(title=title):
                self.assertNotIn(title, html)

    def test_texte_sans_projet_vers_la_note_et_la_recherche(self):
        note = Note.objects.create(date="2026-11-12")
        Passage.objects.create(note=note, content="appeler Paul")
        filed = Note.objects.create(date="2026-11-13")
        Passage.objects.create(note=filed, project=self.project, content="rangé")

        html = self.html()

        self.assertIn("Texte sans projet", html)
        self.assertIn(
            f'href="{reverse("note_taking:note_detail", args=[note.date])}"', html
        )
        self.assertNotIn(
            f'href="{reverse("note_taking:note_detail", args=[filed.date])}"', html
        )
        self.assertIn(
            f'href="{reverse("note_taking:notes_search")}?no_project=on"', html
        )

    def test_taches_sans_projet_hors_bilan(self):
        note = Note.objects.create(date="2026-11-02")
        loose = self.task("À rattacher", project=None, due_date=date(2030, 1, 1))
        self.to_review("Au bilan", note, project=None)

        html = self.html()

        self.assertIn("Tâches sans projet", html)
        self.assertIn(
            f'href="{reverse("todolist:task_detail", args=[loose.pk])}"', html
        )

    def test_au_plus_dix_lignes_puis_le_nombre_des_autres(self):
        for number in range(12):
            self.task(f"Sans date {number:02d}")

        html = self.html()

        self.assertIn("Sans date 09", html)
        self.assertNotIn("Sans date 10", html)
        self.assertIn("et 2 autres", html)

    def test_chaque_rubrique_compte(self):
        for number in range(3):
            self.task(f"Sans date {number}")

        self.assertIn("(3)", self.html())
