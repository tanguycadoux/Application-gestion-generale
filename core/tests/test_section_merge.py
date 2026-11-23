"""Réunir deux niveaux : renommer vers le nom d'un frère existant (#373).

Même parcours en trois temps que le renommage (#299) : le nom (au lieu du refus, la
réunion est annoncée), le bilan (titres à réécrire, sous-niveaux réunis, ce qui
change de niveau), puis l'écriture. Le niveau gardé est celui qui existait déjà.
"""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import levels, merge_plan, merge_section, section_for
from note_taking.models import Note, Passage, SavedSearch
from note_taking.renaming import find_occurrences
from note_taking.services import process_passages
from todolist.models import Task


class MergeTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2026-11-23") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def section(self, *names: str) -> Section:
        section = section_for(self.project, names)
        assert section is not None
        return section

    def url(self, section: Section) -> str:
        return reverse("core:section_rename", args=[self.project.pk, section.pk])

    def keys(self, section: Section) -> list[str]:
        return [o.key for o in find_occurrences(self.project, levels(section))]

    def apply(self, section: Section, name: str, keys: list[str] | None = None):
        return self.client.post(
            self.url(section),
            {"name": name, "headings": self.keys(section) if keys is None else keys},
        )

    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def paths(self) -> list[list[str]]:
        return sorted(levels(section) for section in Section.objects.all())


class MergeSectionTests(MergeTestCase):
    """`merge_section` : la réunion en base, sans les notes."""

    def test_tout_ce_qui_utilise_le_niveau_suit(self):
        gone, keep = self.section("Reunion"), self.section("Réunion")
        task = Task.objects.create(title="T", project=self.project, section=gone)
        passage = Passage.objects.create(
            note=Note.objects.create(date="2026-11-23"),
            project=self.project,
            section=gone,
        )
        search = SavedSearch.objects.create(name="S")
        search.sections.add(gone)

        merge_section(gone, keep)

        task.refresh_from_db()
        passage.refresh_from_db()
        self.assertEqual((task.section_id, passage.section_id), (keep.pk, keep.pk))
        self.assertEqual(list(search.sections.all()), [keep])
        self.assertFalse(Section.objects.filter(pk=gone.pk).exists())

    def test_sous_niveaux_homonymes_reunis_les_autres_deplaces(self):
        gone_prep = self.section("Reunion", "préparation", "Ordre du jour")
        keep_prep = self.section("Réunion", "Préparation")
        self.section("Réunion", "Préparation", "ordre du jour")
        moved = self.section("Reunion", "Preparation")
        task = Task.objects.create(title="T", project=self.project, section=gone_prep)

        merge_section(self.section("Reunion"), self.section("Réunion"))

        self.assertEqual(
            self.paths(),
            [
                ["Réunion"],
                ["Réunion", "Preparation"],
                ["Réunion", "Préparation"],
                ["Réunion", "Préparation", "ordre du jour"],
            ],
        )
        task.refresh_from_db()
        assert task.section is not None
        self.assertEqual(
            levels(task.section), ["Réunion", "Préparation", "ordre du jour"]
        )
        moved.refresh_from_db()
        self.assertEqual(moved.parent, self.section("Réunion"))
        self.assertEqual(keep_prep.name, "Préparation")

    def test_bilan_de_la_reunion(self):
        self.section("Reunion", "préparation", "Ordre du jour")
        self.section("Reunion", "Preparation")
        self.section("Reunion", "Suivi")
        self.section("Réunion", "Préparation", "ordre du jour")

        plan = merge_plan(self.section("Reunion"), self.section("Réunion"))

        self.assertEqual(plan.joined, ["Préparation", "Préparation › ordre du jour"])
        self.assertEqual(plan.moved, ["Preparation", "Suivi"])
        self.assertEqual(plan.close, [("Preparation", "Préparation")])


class NameStepTests(MergeTestCase):
    def test_nom_d_un_frere_annonce_la_reunion(self):
        self.note("# P\n## Reunion de chantier\nx\n## Réunion de chantier\ny")

        response = self.client.get(
            self.url(self.section("Reunion de chantier")),
            {"name": "Réunion de chantier"},
        )

        self.assertContains(
            response,
            "Un niveau « Réunion de chantier » existe déjà ici",
        )
        self.assertContains(response, "Bilan")
        self.assertContains(response, ">Réunir<")
        self.assertNotContains(response, 'id="new-name-error"')

    def test_frere_d_un_autre_parent_n_est_pas_une_reunion(self):
        self.note("# P\n## A\n### Suite\nx\n## B\n### Autre\ny")

        response = self.client.get(
            self.url(self.section("B", "Autre")), {"name": "Suite"}
        )

        self.assertNotContains(response, "existe déjà ici")
        self.assertContains(response, ">Renommer<")


class ReviewStepTests(MergeTestCase):
    def test_bilan_titres_sous_niveaux_et_usages(self):
        self.note(
            "# P\n## Reunion\n### Preparation\n- [ ] Relancer\n### Suivi\nx\n"
            "## Réunion\n### Préparation\ny"
        )
        Task.objects.create(
            title="À la main", project=self.project, section=self.section("Reunion")
        )

        response = self.client.get(
            self.url(self.section("Reunion")), {"name": "réunion"}
        )

        self.assertContains(response, "Bilan : « Reunion » rejoint « Réunion »")
        self.assertContains(response, "1 titre à réécrire")
        # Ce qui change de niveau : passages et tâches, sous-niveaux compris.
        self.assertContains(response, "2 passages et 2 tâches")
        self.assertContains(response, "« Preparation », proche de « Préparation »")
        self.assertContains(response, "Suivi")

    def test_sous_niveaux_reunis_listes(self):
        self.note("# P\n## Reunion\n### préparation\nx\n## Réunion\n### Préparation\ny")

        response = self.client.get(
            self.url(self.section("Reunion")), {"name": "Réunion"}
        )

        self.assertEqual(response.context["plan"].joined, ["Préparation"])


class ApplyStepTests(MergeTestCase):
    def test_tout_reuni(self):
        first = self.note(
            "# P\n## Reunion {#r}\n### Preparation\nx\n### préparation\ny"
        )
        second = self.note("# P\n## Réunion\n### Préparation\nz", day="2026-11-24")
        keep = self.section("Réunion")
        gone = self.section("Reunion")
        manual = Task.objects.create(title="T", project=self.project, section=gone)

        response = self.apply(gone, "réunion")

        self.assertRedirects(
            response, reverse("core:project_paths", args=[self.project.pk])
        )
        first.refresh_from_db()
        second.refresh_from_db()
        # Le nom gardé est celui du niveau qui existait, attributs du titre gardés.
        self.assertEqual(
            first.body, "# P\n## Réunion {#r}\n### Preparation\nx\n### préparation\ny"
        )
        self.assertEqual(second.body, "# P\n## Réunion\n### Préparation\nz")
        self.assertFalse(Section.objects.filter(pk=gone.pk).exists())
        manual.refresh_from_db()
        self.assertEqual(manual.section_id, keep.pk)
        self.assertEqual(
            self.paths(),
            [["Réunion"], ["Réunion", "Preparation"], ["Réunion", "Préparation"]],
        )
        self.assertEqual(
            self.messages(response),
            [
                "Le niveau « Reunion » est réuni avec « Réunion ». "
                "1 titre réécrit dans 1 note."
            ],
        )

    def test_les_taches_des_notes_suivent(self):
        self.note("# P\n## Reunion\n- [ ] Relancer")
        self.note("# P\n## Réunion\n- [ ] Relancer", day="2026-11-24")
        task = Task.objects.get(note_date="2026-11-23")
        task.progress = 40
        task.save()

        self.apply(self.section("Reunion"), "Réunion")

        task.refresh_from_db()
        self.assertEqual((task.note_path, task.progress), ("P › Réunion", 40))
        assert task.section is not None
        self.assertEqual(levels(task.section), ["Réunion"])
        self.assertEqual(Task.objects.count(), 2)

    def test_taches_de_meme_texte_au_meme_chemin_refusees(self):
        """Dans une même note, deux tâches « Relancer » sous « Reunion » et
        « Réunion » n'en feraient plus qu'une (#240) : rien n'est écrit."""
        body = "# P\n## Reunion\n- [ ] Relancer\n## Réunion\n- [ ] Relancer"
        note = self.note(body)
        gone = self.section("Reunion")

        response = self.apply(gone, "Réunion")

        self.assertIn(
            "confondrait deux tâches « Relancer » sous le même chemin",
            self.messages(response)[0],
        )
        note.refresh_from_db()
        self.assertEqual(note.body, body)
        self.assertTrue(Section.objects.filter(pk=gone.pk).exists())
        self.assertEqual(Task.objects.count(), 2)

    def test_reunion_partielle_l_ancien_niveau_garde_ses_notes(self):
        first = self.note("# P\n## Reunion\nx")
        second = self.note("# P\n## Reunion\ny", day="2026-11-24")
        self.note("# P\n## Réunion\nz", day="2026-11-25")
        gone = self.section("Reunion")
        manual = Task.objects.create(title="T", project=self.project, section=gone)
        keep_key, rewrite_key = self.keys(gone)

        self.apply(gone, "Réunion", [rewrite_key])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(
            (first.body, second.body), ("# P\n## Reunion\nx", "# P\n## Réunion\ny")
        )
        self.assertTrue(Section.objects.filter(pk=gone.pk).exists())
        manual.refresh_from_db()
        self.assertEqual(manual.section_id, gone.pk)
        self.assertEqual(keep_key, f"{first.pk}:2")

    def test_niveau_sans_titre_reuni_avec_ses_taches(self):
        keep = self.section("Manuel")
        gone = self.section("Manuels")
        task = Task.objects.create(title="T", project=self.project, section=gone)

        response = self.apply(gone, "manuel")

        self.assertRedirects(
            response, reverse("core:project_paths", args=[self.project.pk])
        )
        task.refresh_from_db()
        self.assertEqual(task.section_id, keep.pk)
        self.assertFalse(Section.objects.filter(pk=gone.pk).exists())

    def test_sous_niveaux_homonymes_des_deux_cotes(self):
        self.note("# P\n## Reunion\n### préparation\n- [ ] A\n#### Ordre\nx")
        self.note(
            "# P\n## Réunion\n### Préparation\n- [ ] B\n#### ordre\ny", day="2026-11-24"
        )

        self.apply(self.section("Reunion"), "Réunion")

        self.assertEqual(
            self.paths(),
            [
                ["Réunion"],
                ["Réunion", "Préparation"],
                ["Réunion", "Préparation", "ordre"],
            ],
        )
        self.assertEqual(
            sorted(Task.objects.values_list("title", "note_path")),
            [("A", "P › Réunion › préparation"), ("B", "P › Réunion › Préparation")],
        )
        for task in Task.objects.all():
            assert task.section is not None
            self.assertEqual(levels(task.section), ["Réunion", "Préparation"])
