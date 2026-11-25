"""L'éditeur signale une note qui a changé depuis son ouverture, sans perdre le texte
saisi (#386)."""

import datetime
import logging
import re
from urllib.parse import unquote

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from note_taking.models import Note
from note_taking.quick_capture import capture
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

    def test_version_dans_le_formulaire(self):
        self.assertTrue(self.opened)
        self.change()
        self.assertNotEqual(self.version(), self.opened)

    def test_note_inchangee_enregistree(self):
        self.assertTrue(self.opened)

        self.save()

        self.assertEqual(self.body(), "# P\nmon texte")

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

    def test_enregistrer_de_nouveau_reste_refuse(self):
        self.change()
        found = VERSION_REGEX.search(self.save().content.decode())
        assert found is not None

        response = self.save(version=found[1])

        self.assertEqual(response.status_code, 409)

    def test_remplacer_expres(self):
        self.change()
        value = self.overwrite_value(self.save().content.decode())

        response = self.save(overwrite=value)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.body(), "# P\nmon texte")

    def test_remplacer_refuse_si_la_note_change_encore(self):
        self.change()
        value = self.overwrite_value(self.save().content.decode())
        self.note.body = "# P\nencore autre"
        self.note.save()

        response = self.save(overwrite=value)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.body(), "# P\nencore autre")

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

    def test_sur_place_deux_fois_de_suite(self):
        """Chaque enregistrement renvoie la version à garder pour le suivant."""
        first = self.save("# P\nun", in_place=True)
        self.assertEqual(first.status_code, 200)

        second = self.save(
            "# P\ndeux", in_place=True, version=first.headers["X-Note-Version"]
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.body(), "# P\ndeux")

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


class ConflictReasonTests(TestCase):
    """Le conflit dit ce qui a changé la note, et quand (#468)."""

    def setUp(self):
        self.day = str(timezone.localdate())
        self.note = Note.objects.create(date=self.day, body="# P\nouvert")
        process_passages(self.note)
        self.url = reverse("note_taking:edit_note", args=[self.day])
        self.opened = self.note.updated.isoformat()

    def save(self, in_place: bool = False, **fields):
        data = {"date": self.day, "body": "x", "version": self.opened, **fields}
        if in_place:
            data["stay"] = "1"
        headers = {"HX-Request": "true"} if in_place else {}
        return self.client.post(self.url, data, headers=headers)

    def time(self, value) -> str:
        return timezone.localtime(value).strftime("%H:%M")

    def test_encadre_nomme_la_capture(self):
        Note.objects.update(updated=timezone.now() - datetime.timedelta(minutes=7))
        self.opened = Note.objects.get().updated.isoformat()
        opened = Note.objects.get().updated
        capture("ligne")
        updated = Note.objects.get().updated

        html = self.save().content.decode()

        self.assertIn(
            f"La note a été modifiée à {self.time(updated)} par la capture rapide", html
        )
        self.assertIn(self.time(opened), html)
        self.assertNotIn("autre onglet…", html)

    def test_meme_minute_avec_les_secondes(self):
        opened = Note.objects.get().updated
        Note.objects.update(
            updated=opened + datetime.timedelta(microseconds=1), updated_by="capture"
        )

        html = self.save().content.decode()

        self.assertIn(f"modifiée à {timezone.localtime(opened):%H:%M:%S} par", html)

    def test_sur_place_la_raison_est_dans_l_en_tete(self):
        capture("ligne")

        response = self.save(in_place=True)

        reason = unquote(response.headers["X-Note-Conflict"])
        self.assertIn("par la capture rapide", reason)

    def test_autre_jour_avec_sa_date(self):
        Note.objects.update(
            updated=timezone.now() - datetime.timedelta(days=40), updated_by="editor"
        )

        html = self.save(version="2020-03-05T10:00:00+00:00").content.decode()

        self.assertIn("5 mars 2020", html)

    def test_source_inconnue_dite_telle_quelle(self):
        self.note.save()

        html = self.save().content.decode()

        self.assertIn("sans que l&#x27;application sache par quoi", html)

    def test_version_sans_modification_connue(self):
        """Version plus récente que celle de la base : aucune écriture ne l'explique."""
        html = self.save(version="2999-01-01T00:00:00+00:00").content.decode()

        self.assertIn("aucune modification connue", html)

    def test_version_illisible(self):
        response = self.save(version="n'importe quoi")

        self.assertEqual(response.status_code, 409)
        self.assertIn("aucune modification connue", response.content.decode())

    def test_log(self):
        capture("ligne")

        with self.assertLogs("note_taking", logging.WARNING) as logs:
            self.save(overwrite="vieux")

        (line,) = [r.getMessage() for r in logs.records]
        self.assertIn(f"Note {self.day}", line)
        self.assertIn(f"ouverte={self.opened}", line)
        self.assertIn(f"enregistrée={Note.objects.get().updated.isoformat()}", line)
        self.assertIn("overwrite=vieux", line)
        self.assertIn("source=capture", line)


class EditorCacheTests(TestCase):
    """Revenir à l'éditeur par Précédent redemande la page, texte et version à jour."""

    def test_editeur_jamais_repris_du_cache(self):
        Note.objects.create(date="2025-11-24", body="x")
        for url in (
            reverse("note_taking:new_note"),
            reverse("note_taking:edit_note", args=["2025-11-24"]),
        ):
            with self.subTest(url=url):
                self.assertIn("no-store", self.client.get(url).headers["Cache-Control"])
