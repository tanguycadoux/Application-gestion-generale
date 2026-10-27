"""Renommer un niveau de chemin : le nom, le bilan, puis l'écriture (#299)."""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import levels, section_for
from note_taking.models import Note
from note_taking.renaming import find_occurrences
from note_taking.services import process_note_parts
from todolist.models import Todo


class RenameTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_note_parts(note)
        return note

    def section(self, name: str) -> Section:
        return Section.objects.get(project=self.project, name=name)

    def url(self, section: Section) -> str:
        return reverse("core:section_rename", args=[self.project.pk, section.pk])

    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]


class NameFormTests(RenameTestCase):
    def test_formulaire_du_nouveau_nom(self):
        self.note("# P\n## Réunion\nx")

        response = self.client.get(self.url(self.section("Réunion")))

        self.assertContains(response, "Renommer « Réunion »")
        self.assertContains(response, 'name="nom"')
        self.assertContains(response, "Nouveau nom")
        self.assertNotContains(response, "Bilan")

    def test_nom_vide_ou_blanc(self):
        self.note("# P\n## Réunion\nx")

        response = self.client.get(self.url(self.section("Réunion")), {"nom": "   "})

        self.assertContains(response, "Écrivez le nouveau nom.")
        self.assertNotContains(response, "Bilan")

    def test_meme_nom(self):
        self.note("# P\n## Réunion\nx")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": " Réunion "}
        )

        self.assertContains(response, "C&#x27;est déjà son nom.")

    def test_nom_deja_pris_sous_le_meme_parent(self):
        self.note("# P\n## Réunion\nx\n## Rencontre\ny")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "rencontre"}
        )

        self.assertContains(response, "existe déjà à cet endroit")
        self.assertContains(response, "fusion")
        self.assertNotContains(response, "Bilan")

    def test_meme_nom_sous_un_autre_parent_permis(self):
        self.note("# P\n## A\n### Suite\nx\n## B\n### Autre\ny")

        response = self.client.get(self.url(self.section("Autre")), {"nom": "Suite"})

        self.assertContains(response, "Bilan")

    def test_changement_de_casse_permis(self):
        self.note("# P\n## Réunion\nx")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "RÉUNION"}
        )

        self.assertContains(response, "Bilan")

    def test_nom_trop_long(self):
        self.note("# P\n## Réunion\nx")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "A" * 201}
        )

        self.assertContains(response, "ne dépasse pas 200 caractères")

    def test_niveau_d_un_autre_projet_introuvable(self):
        other = Project.objects.create(name="Q")
        section = section_for(other, ["A"])
        assert section is not None

        response = self.client.get(
            reverse("core:section_rename", args=[self.project.pk, section.pk])
        )

        self.assertEqual(response.status_code, 404)


class ReviewTests(RenameTestCase):
    def test_bilan_des_titres_avec_cases_cochees(self):
        self.note("# P\n## Réunion\nx\n### Suite\ny")
        self.note("# P\n### Réunion\nz", day="2025-11-25")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "Rencontre"}
        )

        self.assertContains(response, "Bilan : « Réunion » devient « Rencontre »")
        self.assertContains(response, "2 titres à réécrire")
        self.assertContains(response, "Note du 24 novembre 2025, ligne 2")
        self.assertContains(response, "Note du 25 novembre 2025, ligne 2")
        html = response.content.decode()
        self.assertEqual(html.count('name="titres"'), 2)
        self.assertEqual(html.count("checked"), 2)

    def test_les_descendants_ne_sont_pas_des_titres_a_reecrire(self):
        self.note("# P\n## Réunion\nx\n### Suite\ny")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "Rencontre"}
        )

        self.assertContains(response, "1 titre à réécrire")
        self.assertNotContains(response, "ligne 4")

    def test_lien_vers_chaque_note(self):
        note = self.note("# P\n## Réunion\nx")

        response = self.client.get(
            self.url(self.section("Réunion")), {"nom": "Rencontre"}
        )

        self.assertContains(
            response, f'href="{reverse("note_taking:note_detail", args=[note.pk])}"'
        )

    def test_niveau_sans_titre_dans_les_notes(self):
        section = section_for(self.project, ["Manuel"])
        assert section is not None

        response = self.client.get(self.url(section), {"nom": "Autre"})

        self.assertContains(response, "Aucun titre des notes n'a ce nom")
        self.assertNotContains(response, 'name="titres"')

    def test_le_bilan_n_ecrit_rien(self):
        note = self.note("# P\n## Réunion\nx")

        self.client.get(self.url(self.section("Réunion")), {"nom": "Rencontre"})

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n## Réunion\nx")
        self.assertTrue(Section.objects.filter(name="Réunion").exists())

    def test_bouton_de_confirmation_et_annulation(self):
        self.note("# P\n## Réunion\nx")

        html = self.client.get(
            self.url(self.section("Réunion")), {"nom": "Rencontre"}
        ).content.decode()

        self.assertIn('<input type="hidden" name="nom" value="Rencontre">', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn(">Annuler<", html)
        self.assertIn(">Renommer<", html)


class ApplyTests(RenameTestCase):
    def apply(self, section: Section, name: str, keys: list[str] | None = None):
        return self.client.post(self.url(section), {"nom": name, "titres": keys or []})

    def keys(self, section: Section, name: str) -> list[str]:
        return [o.key for o in find_occurrences(self.project, levels(section))]

    def test_tout_renomme_le_niveau_en_place(self):
        note = self.note("# P\n## Réunion\nx\n### Suite\ny")
        section = self.section("Réunion")

        response = self.apply(section, "Rencontre", self.keys(section, "Rencontre"))

        self.assertRedirects(
            response, reverse("core:project_paths", args=[self.project.pk])
        )
        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n## Rencontre\nx\n### Suite\ny")
        section.refresh_from_db()
        self.assertEqual(section.name, "Rencontre")
        # Même niveau, mêmes descendants : rien n'a été recréé.
        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)),
            ["Rencontre", "Suite"],
        )
        self.assertEqual(
            {part.section_id for part in note.parts.all()},
            {section.pk, self.section("Suite").pk},
        )

    def test_message_de_compte_rendu(self):
        self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")

        response = self.apply(section, "Rencontre", self.keys(section, "Rencontre"))

        self.assertEqual(
            self.messages(response),
            [
                "Le niveau « Réunion » est renommé « Rencontre ». 1 titre réécrit dans 1 note."
            ],
        )

    def test_tache_saisie_a_la_main_suit_le_niveau_renomme_en_place(self):
        self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")
        todo = Todo.objects.create(title="T", project=self.project, section=section)

        self.apply(section, "Rencontre", self.keys(section, "Rencontre"))

        todo.refresh_from_db()
        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Rencontre"])

    def test_partiel_l_ancien_et_le_nouveau_niveau_coexistent(self):
        first = self.note("# P\n## Réunion\nx")
        second = self.note("# P\n## Réunion\ny", day="2025-11-25")
        section = self.section("Réunion")
        keep, rename = self.keys(section, "Rencontre")

        self.apply(section, "Rencontre", [rename])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(
            (first.body, second.body), ("# P\n## Réunion\nx", "# P\n## Rencontre\ny")
        )
        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)),
            ["Rencontre", "Réunion"],
        )
        # L'ancien niveau garde sa ligne, donc ses tâches saisies à la main.
        section.refresh_from_db()
        self.assertEqual(section.name, "Réunion")
        self.assertEqual(keep, f"{first.pk}:2")

    def test_niveau_sans_titre_renomme_avec_ses_taches(self):
        section = section_for(self.project, ["Manuel"])
        assert section is not None
        todo = Todo.objects.create(title="T", project=self.project, section=section)

        response = self.apply(section, "Autre")

        self.assertRedirects(
            response, reverse("core:project_paths", args=[self.project.pk])
        )
        section.refresh_from_db()
        todo.refresh_from_db()
        self.assertEqual((section.name, todo.section_id), ("Autre", section.pk))

    def test_note_changee_depuis_le_bilan_rien_n_est_ecrit(self):
        note = self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")
        keys = self.keys(section, "Rencontre")
        note.body = "# P\n## Autre\nx"
        note.save()

        response = self.apply(section, "Rencontre", keys)

        self.assertRedirects(
            response,
            f"{self.url(section)}?nom=Rencontre",
            fetch_redirect_response=False,
        )
        self.assertIn("Une note a changé depuis le bilan", self.messages(response)[0])
        note.refresh_from_db()
        section.refresh_from_db()
        self.assertEqual((note.body, section.name), ("# P\n## Autre\nx", "Réunion"))

    def test_echec_annule_aussi_le_renommage_en_place(self):
        self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")
        keys = self.keys(section, "Rencontre")
        Note.objects.update(body="# P\n## Autre\nx")

        self.apply(section, "Rencontre", keys)

        section.refresh_from_db()
        self.assertEqual(section.name, "Réunion")

    def test_nom_deja_pris_refuse_aussi_a_l_ecriture(self):
        self.note("# P\n## Réunion\nx\n## Rencontre\ny")
        section = self.section("Réunion")

        response = self.apply(section, "Rencontre", self.keys(section, "Rencontre"))

        self.assertContains(response, "existe déjà à cet endroit")
        self.assertEqual(Note.objects.get().body, "# P\n## Réunion\nx\n## Rencontre\ny")

    def test_sans_nom_rien_n_est_ecrit(self):
        note = self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")

        response = self.client.post(
            self.url(section), {"titres": self.keys(section, "")}
        )

        self.assertContains(response, "Nouveau nom")
        note.refresh_from_db()
        self.assertEqual(note.body, "# P\n## Réunion\nx")

    def test_changement_de_casse(self):
        note = self.note("# P\n## Réunion\nx")
        section = self.section("Réunion")

        self.apply(section, "RÉUNION", self.keys(section, "RÉUNION"))

        note.refresh_from_db()
        section.refresh_from_db()
        self.assertEqual((note.body, section.name), ("# P\n## RÉUNION\nx", "RÉUNION"))
