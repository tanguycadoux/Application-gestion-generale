"""L'éditeur signale une note qui a changé depuis son ouverture, sans perdre le texte
saisi (#386)."""

import re
from unittest import expectedFailure

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages

VERSION_REGEX = re.compile(r'<input type="hidden" name="version" value="([^"]+)"')


class EditConflictTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nouvert")
        process_passages(self.note)
        self.url = reverse("note_taking:edit_note", args=["2025-11-24"])
        self.opened = self.version()

    def version(self) -> str:
        found = VERSION_REGEX.search(self.client.get(self.url).content.decode())
        return found[1] if found else ""

    def change(self) -> None:
        """La note change ailleurs, par exemple par la capture rapide."""
        self.note.body = "# P\nouvert\n\ncapturé"
        self.note.save()

    def save(self, body: str = "# P\nmon texte", in_place: bool = False, **fields):
        data = {"date": "2025-11-24", "body": body, "version": self.opened, **fields}
        headers = {"HX-Request": "true"} if in_place else {}
        if in_place:
            data["stay"] = "1"
        return self.client.post(self.url, data, headers=headers)

    def overwrite_value(self, html: str) -> str:
        found = re.search(r'name="overwrite" value="([^"]+)"', html)
        assert found is not None
        return found[1]

    def body(self) -> str:
        return Note.objects.get().body

    @expectedFailure
    def test_version_dans_le_formulaire(self):
        self.assertTrue(self.opened)
        self.change()
        self.assertNotEqual(self.version(), self.opened)

    @expectedFailure
    def test_note_inchangee_enregistree(self):
        self.assertTrue(self.opened)

        self.save()

        self.assertEqual(self.body(), "# P\nmon texte")

    @expectedFailure
    def test_note_changee_rien_n_est_ecrit_et_le_texte_revient(self):
        self.change()

        response = self.save()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.body(), "# P\nouvert\n\ncapturé")
        html = response.content.decode()
        self.assertRegex(html, r"<textarea[^>]*>\s*# P\nmon texte</textarea>")
        self.assertIn("data-unsaved", html)
        self.assertRegex(html, r"<div (?![^>]*\bhidden\b)[^>]*data-note-conflict")
        # La version enregistrée s'ouvre à côté.
        self.assertIn('target="_blank"', html)

    @expectedFailure
    def test_enregistrer_de_nouveau_reste_refuse(self):
        self.change()
        found = VERSION_REGEX.search(self.save().content.decode())
        assert found is not None

        response = self.save(version=found[1])

        self.assertEqual(response.status_code, 409)

    @expectedFailure
    def test_remplacer_expres(self):
        self.change()
        value = self.overwrite_value(self.save().content.decode())

        response = self.save(overwrite=value)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.body(), "# P\nmon texte")

    @expectedFailure
    def test_remplacer_refuse_si_la_note_change_encore(self):
        self.change()
        value = self.overwrite_value(self.save().content.decode())
        self.note.body = "# P\nencore autre"
        self.note.save()

        response = self.save(overwrite=value)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.body(), "# P\nencore autre")

    @expectedFailure
    def test_sur_place(self):
        self.change()

        response = self.save(in_place=True)

        self.assertEqual(response.status_code, 409)
        self.assertIn("data-toast", response.content.decode())
        self.assertEqual(self.body(), "# P\nouvert\n\ncapturé")

        replaced = self.save(
            in_place=True, overwrite=response.headers["X-Note-Version"]
        )

        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(self.body(), "# P\nmon texte")

    @expectedFailure
    def test_sur_place_deux_fois_de_suite(self):
        """Chaque enregistrement renvoie la version à garder pour le suivant."""
        first = self.save("# P\nun", in_place=True)
        self.assertEqual(first.status_code, 200)

        second = self.save(
            "# P\ndeux", in_place=True, version=first.headers["X-Note-Version"]
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.body(), "# P\ndeux")

    @expectedFailure
    def test_titre_de_projet_renomme_version_a_jour(self):
        """Les suites de l'enregistrement ne rendent pas la version périmée."""
        first = self.save("# Q\nun", in_place=True)

        self.assertEqual(first.headers["X-Note-Version"], self.version())

    def test_sans_version_enregistree_comme_avant(self):
        self.change()

        self.client.post(self.url, {"date": "2025-11-24", "body": "# P\nz"})

        self.assertEqual(self.body(), "# P\nz")

    def test_nouvelle_note_sans_version(self):
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assertNotIn('name="version"', html)
