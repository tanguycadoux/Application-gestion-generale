"""Titres qui sautent un niveau, signalés sans réécrire la note (#305).

`# A` puis `### B` donne le chemin « A › B » : le modèle l'accepte. L'utilisateur
en est prévenu à l'enregistrement et dans le compte rendu d'import ; le texte de la
note n'est jamais modifié.
"""

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.qmd.parser import parse_note
from note_taking.services import process_note_parts


def warnings(raw: str) -> list[str]:
    return parse_note("2025-11-24", raw).warnings


class SkippedLevelParserTests(SimpleTestCase):
    def test_un_niveau_saute(self):
        self.assertEqual(
            warnings("# A\n### B\nx"),
            ["Ligne 2 : le titre « B » (###) saute un niveau sous « A » (#)."],
        )

    def test_aucun_avertissement_sans_saut(self):
        self.assertEqual(warnings("# A\n## B\n### C\n#### D\nx"), [])

    def test_plusieurs_niveaux_sautes_un_seul_avertissement(self):
        self.assertEqual(
            warnings("# A\n##### B"),
            ["Ligne 2 : le titre « B » (#####) saute un niveau sous « A » (#)."],
        )

    def test_sous_le_titre_le_plus_profond(self):
        self.assertEqual(
            warnings("# A\n## B\n#### C"),
            ["Ligne 3 : le titre « C » (####) saute un niveau sous « B » (##)."],
        )

    def test_un_titre_moins_profond_repart_de_zero(self):
        self.assertEqual(
            warnings("# A\n## B\n### C\n# D\n### E"),
            ["Ligne 5 : le titre « E » (###) saute un niveau sous « D » (#)."],
        )

    def test_remonter_de_plusieurs_niveaux_n_est_pas_un_saut(self):
        self.assertEqual(warnings("# A\n## B\n### C\n#### D\n## E"), [])

    def test_chaque_saut_est_signale(self):
        raw = "# A\n### B\nx\n# C\n### D\ny"

        self.assertEqual(len(warnings(raw)), 2)

    def test_titre_sans_projet(self):
        self.assertEqual(
            warnings("## S\nx\n# P\ny"),
            [
                "Ligne 1 : le titre « S » (##) n'a pas de projet (#) au-dessus de "
                "lui : son contenu n'est pas enregistré."
            ],
        )

    def test_texte_sans_titre_avant_le_projet_n_est_pas_signale(self):
        self.assertEqual(warnings("intro\n# P\nx"), [])

    def test_titres_d_un_bloc_de_code_ou_d_un_callout_ignores(self):
        raw = '# A\n```\n### B\n```\n::: {.callout-note title="t"}\n### C\n:::\nx'

        self.assertEqual(warnings(raw), [])

    def test_sept_diese_n_est_pas_un_titre(self):
        self.assertEqual(warnings("# A\n####### B"), [])

    def test_le_texte_est_analyse_comme_avant(self):
        note = parse_note("2025-11-24", "# A\n### B\nx")

        self.assertEqual(
            [(part.path, part.lines) for part in note.parts], [(["B"], ["x"])]
        )

    def test_json_historique_inchange(self):
        self.assertNotIn(
            "warnings", parse_note("2025-11-24", "# A\n### B\nx").as_dict()
        )


class SkippedLevelServiceTests(TestCase):
    def test_avertissements_de_la_note(self):
        note = Note.objects.create(date="2025-11-24", body="# A\n### B\nx")

        process_note_parts(note)

        self.assertEqual(len(note.warnings), 1)
        self.assertIn("saute un niveau", note.warnings[0])

    def test_note_sans_saut(self):
        note = Note.objects.create(date="2025-11-24", body="# A\n## B\nx")

        process_note_parts(note)

        self.assertEqual(note.warnings, ())

    def test_le_texte_de_la_note_n_est_pas_reecrit(self):
        note = Note.objects.create(date="2025-11-24", body="# A\n### B\nx")

        process_note_parts(note)

        note.refresh_from_db()
        self.assertEqual(note.body, "# A\n### B\nx")


class SkippedLevelMessagesTests(TestCase):
    def messages(self, response) -> list[str]:
        return [str(m) for m in get_messages(response.wsgi_request)]

    def create(self, body: str) -> list[str]:
        response = self.client.post(
            reverse("note_taking:new_note"), {"date": "2025-11-24", "body": body}
        )
        return self.messages(response)

    def test_creation_succes_puis_avertissement(self):
        messages = self.create("# A\n### B\nx")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], "La note du 24 novembre 2025 est créée.")
        self.assertIn("Ligne 2 : le titre « B » (###) saute un niveau", messages[1])

    def test_avertissement_de_niveau_warning(self):
        response = self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2025-11-24", "body": "# A\n### B\nx"},
        )

        levels = [m.level_tag for m in get_messages(response.wsgi_request)]
        self.assertEqual(levels, ["success", "warning"])

    def test_pas_d_avertissement_sans_saut(self):
        self.assertEqual(
            self.create("# A\n## B\nx"), ["La note du 24 novembre 2025 est créée."]
        )

    def test_plusieurs_sauts_resumes(self):
        messages = self.create("# A\n### B\n# C\n### D\n# E\n### F")

        self.assertEqual(len(messages), 2)
        self.assertIn("Ligne 2", messages[1])
        self.assertIn("2 autres titres", messages[1])
        self.assertNotIn("Ligne 4", messages[1])

    def test_un_seul_autre_au_singulier(self):
        messages = self.create("# A\n### B\n# C\n### D")

        self.assertIn("1 autre titre", messages[1])

    def test_modification(self):
        note = Note.objects.create(date="2025-11-24", body="# A\nx")

        response = self.client.post(
            reverse("note_taking:edit_note", args=[note.date]),
            {"date": "2025-11-24", "body": "# A\n### B\nx"},
        )

        messages = self.messages(response)
        self.assertEqual(messages[0], "La note du 24 novembre 2025 est modifiée.")
        self.assertIn("saute un niveau", messages[1])

    def test_remplacement_par_le_fichier_source(self):
        note = Note.objects.create(date="2025-11-24", body="# A\nx")
        file = SimpleUploadedFile(
            "2025-11-24.qmd", b"---\ndate: 2025-11-24\n---\n# A\n### B\ny"
        )

        response = self.client.post(
            reverse("note_taking:update_source_file", args=[note.date]),
            {"note_update_source_file": file},
        )

        self.assertIn("saute un niveau", self.messages(response)[1])

    def test_note_non_traitee_sans_avertissement(self):
        messages = self.create("# A\n### B\n![a](absente.png)")

        self.assertEqual(len(messages), 1)
        self.assertIn("n'a pas pu être traité", messages[0])


class SkippedLevelImportTests(TestCase):
    def post(self, body: str):
        file = SimpleUploadedFile(
            "2025-11-24.qmd", f"---\ndate: 2025-11-24\n---\n\n{body}".encode()
        )
        return self.client.post(
            reverse("note_taking:import_files"), {"import_files": [file]}
        )

    def test_compte_rendu_liste_les_avertissements(self):
        response = self.post("# A\n### B\nx")

        self.assertContains(response, "Notes créées (1)")
        self.assertContains(response, "saute un niveau sous « A » (#)")

    def test_compte_rendu_sans_avertissement(self):
        response = self.post("# A\n## B\nx")

        self.assertNotContains(response, "saute un niveau")
