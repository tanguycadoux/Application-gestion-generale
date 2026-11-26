"""Ce qui a changé dans la version enregistrée, montré dans l'encadré de conflit
(#471)."""

import re
from urllib.parse import unquote

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages
from note_taking.text_merge import describe_changes


class DescribeChangesTests(SimpleTestCase):
    def test_ligne_ajoutee_sous_son_titre(self):
        (change,) = describe_changes("# P\n## R\na", "# P\n## R\na\nb")

        self.assertEqual(change.where, "P › R")
        self.assertEqual(change.added, ["b"])
        self.assertEqual(change.removed, [])
        self.assertEqual(change.summary, "1 ligne ajoutée")

    def test_ligne_modifiee(self):
        (change,) = describe_changes("# P\na\nb", "# P\nA\nb")

        self.assertEqual((change.added, change.removed), (["A"], ["a"]))
        self.assertEqual(change.summary, "1 ligne ajoutée, 1 retirée")

    def test_plusieurs_endroits(self):
        changes = describe_changes("# P\na\n# Q\nb", "# P\na\nx\n# Q\nb\ny\nz")

        self.assertEqual([c.where for c in changes], ["P", "Q"])
        self.assertEqual(changes[1].summary, "2 lignes ajoutées")

    def test_avant_le_premier_titre(self):
        (change,) = describe_changes("# P\na", "intro\n# P\na")

        self.assertEqual(change.where, "")

    def test_titre_ajoute_nomme_son_parent(self):
        (change,) = describe_changes("# P\na", "# P\na\n## Nouveau\nb")

        self.assertEqual(change.where, "P")
        self.assertEqual(change.added, ["## Nouveau", "b"])

    def test_titre_dans_un_bloc_de_code_ignore(self):
        (change,) = describe_changes(
            "# P\n```\n# pas un titre\n```\na", "# P\n```\n# pas un titre\n```\na\nb"
        )

        self.assertEqual(change.where, "P")

    def test_lignes_vides_seules_ignorees(self):
        self.assertEqual(describe_changes("# P\na", "# P\n\na\n"), [])

    def test_fins_de_ligne_windows(self):
        self.assertEqual(describe_changes("# P\r\na", "# P\na"), [])
        (change,) = describe_changes("# P\r\na", "# P\r\na\r\nb")
        self.assertEqual(change.added, ["b"])


class ConflictChangesViewTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nouvert")
        process_passages(self.note)
        self.url = reverse("note_taking:edit_note", args=["2025-11-24"])
        html = self.client.get(self.url).content.decode()
        self.opened = re.search(r'name="version" value="([^"]+)"', html)[1]
        self.html = html

    def change(self, body: str) -> None:
        self.note.body = body
        self.note.save()

    def save(self, body: str, in_place: bool = False, **fields):
        data = {
            "date": "2025-11-24",
            "body": body,
            "version": self.opened,
            "original": "# P\nouvert",
            **fields,
        }
        headers = {"HX-Request": "true"} if in_place else {}
        if in_place:
            data["stay"] = "1"
        return self.client.post(self.url, data, headers=headers)

    def test_texte_d_origine_dans_le_formulaire(self):
        self.assertRegex(
            self.html, r'<textarea name="original" hidden>\n# P\nouvert</textarea>'
        )

    def test_encadre_montre_les_lignes_ajoutees(self):
        self.change("# P\nouvert\n<b>capturé</b>")

        response = self.save("# P\nmon texte")

        self.assertEqual(response.status_code, 409)
        html = response.content.decode()
        self.assertIn("1 ligne ajoutée", html)
        self.assertIn("« P »", html)
        self.assertIn("&lt;b&gt;capturé&lt;/b&gt;", html)
        self.assertNotIn("<b>capturé</b>", html)
        # Le texte d'origine envoyé reste celui du formulaire.
        self.assertRegex(html, r'<textarea name="original" hidden>\n# P\nouvert</')

    def test_sans_texte_d_origine_pas_de_differences(self):
        self.change("# P\nouvert\ncapturé")

        response = self.client.post(
            self.url,
            {"date": "2025-11-24", "body": "# P\nz", "version": self.opened},
        )

        self.assertEqual(response.status_code, 409)
        html = response.content.decode()
        self.assertNotIn("ligne ajoutée", html)
        self.assertNotIn('name="original"', html)

    def test_sur_place_les_differences_dans_la_reponse(self):
        self.change("# P\nouvert\ncapturé")

        response = self.save("# P\nmon texte", in_place=True)

        self.assertEqual(response.status_code, 409)
        html = response.content.decode()
        self.assertIn("data-toast", html)
        self.assertRegex(html, r"<template data-conflict-changes>(.|\n)*capturé")
        self.assertTrue(unquote(response.headers["X-Note-Conflict"]))
