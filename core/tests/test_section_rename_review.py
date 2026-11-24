"""Le bilan d'un renommage de niveau dit ce que contient chaque titre, ce qui suit, et
où le même nom existe ailleurs (#376)."""

import re

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import app_registry
from core.models import Project, Section
from core.sections import section_for
from note_taking.models import Note
from note_taking.renaming import find_occurrences
from note_taking.services import process_passages
from todolist.models import Task


class ReviewTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def section(self, *names: str, project: Project | None = None) -> Section:
        section = section_for(project or self.project, names)
        assert section is not None
        return section

    def url(self, section: Section) -> str:
        return reverse("core:section_rename", args=[section.project_id, section.pk])

    def review(self, *names: str, name: str = "Nouveau") -> str:
        response = self.client.get(self.url(self.section(*names)), {"name": name})
        return response.content.decode()


class ExcerptTests(ReviewTestCase):
    def excerpts(self, body: str) -> list[str]:
        self.note(body)
        return [found.excerpt for found in find_occurrences(self.project, ["A"])]

    def test_premiers_mots_de_chaque_section(self):
        self.assertEqual(
            self.excerpts("# P\n## A\n\nPremier texte\nsuite\n## A\nSecond texte"),
            ["Premier texte", "Second texte"],
        )

    def test_texte_sans_marques(self):
        self.assertEqual(
            self.excerpts("# P\n## A\n- [ ] Voir [le plan](https://x.fr/a)"),
            ["Voir le plan"],
        )

    def test_blocs_et_lignes_sans_texte_passes(self):
        body = (
            "# P\n## A\n::: {.metadata}\ntags: [x]\n:::\n---\n![](https://x.fr/a.png)\n"
            "::: {.callout-note}\nDans l'encadré\n:::"
        )
        self.assertEqual(self.excerpts(body), ["Dans l'encadré"])

    def test_section_de_sous_titres_seulement(self):
        self.assertEqual(
            self.excerpts("# P\n## A\n### B\nTexte de B\n## C\nAilleurs"),
            ["Texte de B"],
        )

    def test_section_vide(self):
        """Le texte de la section suivante n'est pas le sien."""
        self.assertEqual(self.excerpts("# P\n## A\n## C\nAilleurs"), [""])

    def test_raccourci(self):
        [excerpt] = self.excerpts("# P\n## A\n" + "mot " * 100)

        self.assertLess(len(excerpt), 170)
        self.assertTrue(excerpt.endswith("…"))

    def test_affiche_et_echappe(self):
        self.note("# P\n## A\nUn <b>texte</b>")

        self.assertIn("Un &lt;b&gt;texte&lt;/b&gt;", self.review("A"))


class OccurrenceTasksTests(ReviewTestCase):
    def tasks(self) -> list[tuple[str, ...]]:
        return [found.tasks for found in find_occurrences(self.project, ["A"])]

    def test_taches_de_chaque_titre_sous_titres_compris(self):
        self.note(
            "# P\n## A\n- [ ] Une\n### B\n- [ ] Deux\n## C\n- [ ] Trois\n"
            "## A\n- [ ] Quatre"
        )
        self.note("# P\n## A\nx", day="2025-11-25")

        self.assertEqual(self.tasks(), [("Une", "Deux"), ("Quatre",), ()])

    def test_titre_de_la_tache_et_non_sa_ligne(self):
        self.note("# P\n## A\n- [ ] Une")
        Task.objects.update(title="Renommée")

        self.assertEqual(self.tasks(), [("Renommée",)])

    def test_tache_ecartee_absente(self):
        self.note("# P\n## A\n- [ ] Une")
        Task.objects.update(note_state=Task.NoteState.DISMISSED)

        self.assertEqual(self.tasks(), [()])

    def test_affichees_sous_leur_titre(self):
        self.note("# P\n## A\n- [ ] Une\n- [ ] Deux")

        self.assertIn("2 tâches : Une, Deux", self.review("A"))

    def test_nombre_de_requetes_constant(self):
        def count() -> int:
            with CaptureQueriesContext(connection) as captured:
                find_occurrences(self.project, ["A"])
            return len(captured)

        self.note("# P\n## A\n- [ ] Une")
        before = count()
        for day in range(1, 8):
            self.note("# P\n## A\n- [ ] Une", day=f"2025-12-0{day}")

        self.assertEqual(count(), before)
        self.assertEqual(sum(len(titles) for titles in self.tasks()), 8)


class TasksTextTests(SimpleTestCase):
    def text(self, *tasks: str) -> str:
        return app_registry.HeadingOccurrence("", "", "", "", tasks=tasks).tasks_text

    def test_texte(self):
        self.assertEqual(self.text(), "")
        self.assertEqual(self.text("Une"), "1 tâche : Une")
        self.assertEqual(
            self.text("Une", "Deux", "Trois"), "3 tâches : Une, Deux, Trois"
        )

    def test_au_dela_de_trois(self):
        self.assertEqual(self.text("1", "2", "3", "4"), "4 tâches : 1, 2, 3 et 1 autre")
        self.assertEqual(
            self.text("1", "2", "3", "4", "5"), "5 tâches : 1, 2, 3 et 2 autres"
        )

    def test_titre_long_raccourci(self):
        self.assertLess(len(self.text("x" * 300)), 90)


class FollowersTests(ReviewTestCase):
    def test_ce_qui_suit_le_nouveau_chemin(self):
        """Comme la page Chemins : sous-niveaux et tâches saisies à la main compris."""
        self.note("# P\n## A\n- [ ] Une\n### B\n- [ ] Deux")
        Task.objects.create(
            title="Main", project=self.project, section=self.section("A")
        )

        self.assertIn(
            "sous-niveaux compris : 2 passages et 3 tâches.", self.review("A")
        )

    def test_rien_ne_suit(self):
        self.section("A")

        self.assertNotIn("sous-niveaux compris", self.review("A"))


class HomonymTests(ReviewTestCase):
    def homonyms(self, html: str) -> list[tuple[str, str]]:
        """Chemin et adresse de chaque homonyme proposé."""
        found = re.search(r'aria-labelledby="homonyms-title".*?</section>', html, re.S)
        if found is None:
            return []
        return re.findall(
            r'<li[^>]*>\s*(.*?)\s*<span[^>]*><a[^>]*href="([^"]*)"', found[0], re.S
        )

    def test_autres_parents_et_autres_projets_casse_et_accents_ignores(self):
        other = Project.objects.create(name="Q")
        under = self.section("Suivi", "Reunion")
        elsewhere = self.section("RÉUNION", project=other)
        self.section("Réunions")

        self.assertEqual(
            self.homonyms(self.review("Réunion", name="Point")),
            [
                ("P › Suivi › Reunion", f"{self.url(under)}?name=Point"),
                ("Q › RÉUNION", f"{self.url(elsewhere)}?name=Point"),
            ],
        )

    def test_nouveau_nom_encode(self):
        under = self.section("Suivi", "A")

        self.assertEqual(
            self.homonyms(self.review("A", name="R&D #1")),
            [("P › Suivi › A", f"{self.url(under)}?name=R%26D+%231")],
        )

    def test_deja_au_nouveau_nom(self):
        self.section("Suivi", "Réunion")

        self.assertEqual(self.homonyms(self.review("réunion", name="Réunion")), [])

    def test_le_frere_de_la_reunion_n_en_est_pas_un(self):
        self.section("Réunion")

        self.assertEqual(self.homonyms(self.review("Reunion", name="Réunion")), [])

    def test_aucun_homonyme(self):
        self.section("Autre")

        self.assertNotIn("Ailleurs, le même nom", self.review("A"))


class HeaderTests(ReviewTestCase):
    def test_separateur_entre_le_projet_et_le_chemin(self):
        section = self.section("A", "B")

        html = self.client.get(self.url(section)).content.decode()

        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        self.assertIn("P › A › B", text)
        self.assertNotIn("P · A", text)
