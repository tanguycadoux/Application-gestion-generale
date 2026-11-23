"""Un titre de projet changé dans l'éditeur d'une note (#170) : un bilan fait choisir
de tout renommer, de ne renommer que dans cette note, ou de ne pas renommer."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, PendingProjectRename
from note_taking.project_renaming import renamed_projects
from note_taking.services import process_passages
from todolist.models import Task


class RenamedProjectsTests(SimpleTestCase):
    def test_titre_de_projet_change(self):
        self.assertEqual(
            renamed_projects("# A\nx\n# B\ny", "# C\nx\n# B\ny"), [("A", "C")]
        )

    def test_rien_de_change(self):
        self.assertEqual(renamed_projects("# A\nx", "# A\nx et y"), [])

    def test_casse_seule_n_est_pas_un_renommage(self):
        """Un nom de projet ignore la casse (#374) : c'est le même projet."""
        self.assertEqual(renamed_projects("# Alpha\nx", "# ALPHA\nx"), [])

    def test_nombre_de_projets_change(self):
        self.assertEqual(renamed_projects("# A\nx", "# C\nx\n# B\ny"), [])

    def test_echange_de_deux_titres(self):
        self.assertEqual(renamed_projects("# A\nx\n# B\ny", "# B\nx\n# A\ny"), [])

    def test_meme_renommage_ecrit_deux_fois(self):
        self.assertEqual(
            renamed_projects("# A\nx\n# A\ny", "# C\nx\n# C\ny"), [("A", "C")]
        )

    def test_niveaux_ignores(self):
        self.assertEqual(renamed_projects("# A\n## R\nx", "# A\n## S\nx"), [])


class InNoteRenameTestCase(TestCase):
    BODY = "# Alpha\n## Réunion\n- [ ] Écrire\n"

    def setUp(self):
        self.alpha = Project.objects.create(name="Alpha", color="blue")
        self.note = self.save_note("2025-11-24", self.BODY)
        self.other = self.save_note("2025-11-25", "# Alpha\nz\n")
        self.task = Task.objects.get(note_line_text="Écrire")

    def save_note(self, day, body):
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def edit(self, body, stay=False):
        data = {"date": "2025-11-24", "body": body}
        if stay:
            data["stay"] = "1"
        return self.client.post(
            reverse("note_taking:edit_note", args=["2025-11-24"]), data
        )

    def review_url(self):
        return reverse("note_taking:project_rename_review", args=["2025-11-24"])

    def choose(self, choice):
        pending = PendingProjectRename.objects.get(note=self.note)
        return self.client.post(self.review_url(), {f"choice-{pending.pk}": choice})


class DetectionTests(InNoteRenameTestCase):
    def test_bilan_apres_l_enregistrement(self):
        response = self.edit(self.BODY.replace("# Alpha", "# Gamma"))

        self.assertRedirects(response, self.review_url(), fetch_redirect_response=False)
        pending = PendingProjectRename.objects.get(note=self.note)
        self.assertEqual((pending.old_name, pending.new_name), ("Alpha", "Gamma"))

    def test_les_taches_suivent_sans_doublon(self):
        self.edit(self.BODY.replace("# Alpha", "# Gamma"))

        self.assertEqual(Task.objects.filter(note_line_text="Écrire").count(), 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.project.name, "Gamma")
        self.assertTrue(self.task.note_path.startswith("Gamma"))

    def test_vers_un_projet_existant_pas_de_bilan(self):
        """Écrire le nom d'un projet qui existe, c'est y ranger le texte."""
        Project.objects.create(name="Beta")

        response = self.edit(self.BODY.replace("# Alpha", "# Beta"))

        self.assertFalse(PendingProjectRename.objects.exists())
        self.assertNotEqual(response.url, self.review_url())

    def test_garde_entre_deux_enregistrements_dans_l_editeur(self):
        """Ctrl+S reste dans l'éditeur ; le bilan vient à « Terminer l'édition »."""
        body = self.BODY.replace("# Alpha", "# Gamma")
        self.edit(body, stay=True)

        response = self.edit(body)

        self.assertRedirects(response, self.review_url(), fetch_redirect_response=False)

    def test_renommages_enchaines(self):
        self.edit(self.BODY.replace("# Alpha", "# Gamma"), stay=True)
        self.edit(self.BODY.replace("# Alpha", "# Delta"), stay=True)

        pending = PendingProjectRename.objects.get(note=self.note)
        self.assertEqual((pending.old_name, pending.new_name), ("Alpha", "Delta"))

    def test_retour_a_l_ancien_nom(self):
        self.edit(self.BODY.replace("# Alpha", "# Gamma"), stay=True)
        self.edit(self.BODY, stay=True)

        self.assertFalse(PendingProjectRename.objects.exists())


class ReviewTests(InNoteRenameTestCase):
    def setUp(self):
        super().setUp()
        self.edit(self.BODY.replace("# Alpha", "# Gamma"))

    def test_trois_choix(self):
        response = self.client.get(self.review_url())

        html = response.content.decode()
        self.assertIn("Alpha", html)
        self.assertIn("Gamma", html)
        self.assertIn('value="everywhere"', html)
        self.assertIn('value="here"', html)
        self.assertIn('value="undo"', html)
        # Par défaut, ce qui est enregistré : seulement dans cette note.
        self.assertRegex(html, r'value="here"[^>]*checked')
        self.assertIn("1 autre note", html)

    def test_tout_renommer(self):
        response = self.choose("everywhere")

        self.assertNotEqual(response.url, self.review_url())
        self.assertFalse(PendingProjectRename.objects.exists())
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.name, "Gamma")
        self.assertEqual(self.alpha.color, "blue")
        self.assertEqual(Project.objects.filter(name__iexact="gamma").count(), 1)
        self.assertFalse(Project.objects.filter(name__iexact="alpha").exists())
        self.other.refresh_from_db()
        self.assertEqual(self.other.body, "# Gamma\nz\n")
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.alpha)
        self.assertEqual(
            set(self.alpha.passages.values_list("note", flat=True)),
            {self.note.pk, self.other.pk},
        )

    def test_seulement_dans_cette_note(self):
        self.choose("here")

        self.assertFalse(PendingProjectRename.objects.exists())
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.name, "Alpha")
        self.other.refresh_from_db()
        self.assertEqual(self.other.body, "# Alpha\nz\n")
        self.assertTrue(Project.objects.filter(name="Gamma").exists())

    def test_ne_pas_renommer(self):
        self.choose("undo")

        self.assertFalse(PendingProjectRename.objects.exists())
        self.note.refresh_from_db()
        self.assertEqual(self.note.body, self.BODY.rstrip("\n"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.project, self.alpha)
        self.assertTrue(self.task.note_path.startswith("Alpha"))
        self.assertFalse(Project.objects.filter(name="Gamma").exists())

    def test_sans_renommage_en_attente(self):
        PendingProjectRename.objects.all().delete()

        response = self.client.get(self.review_url())

        self.assertRedirects(
            response,
            reverse("note_taking:note_detail", args=["2025-11-24"]),
            fetch_redirect_response=False,
        )
