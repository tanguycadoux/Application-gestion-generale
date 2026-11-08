"""Enregistrer une note sans quitter l'éditeur (#389).

Le bouton « Enregistrer la note » (et Ctrl+S) envoie `stay=1` : en arrière-plan
(requête htmx), la vue répond par les toasts, sans redirection ; sans JavaScript,
elle revient à l'éditeur. « Terminer l'édition » garde le comportement d'avant :
la page de la note, ou le bilan des tâches.
"""

import re

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note


def edit_url(note_date: str) -> str:
    return reverse("note_taking:edit_note", args=[note_date])


class SaveInPlaceHtmxTests(TestCase):
    """Enregistrement en arrière-plan : la page de l'éditeur ne change pas."""

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")

    def post(self, body: str, **data):
        return self.client.post(
            edit_url("2025-11-24"),
            {"date": "2025-11-24", "body": body, "stay": "1", **data},
            HTTP_HX_REQUEST="true",
        )

    def test_enregistre_sans_redirection(self):
        response = self.post("# P\ny")

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "# P\ny")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.note.parts.values_list("content", flat=True)), ["y"])

    def test_repond_par_les_toasts(self):
        response = self.post("# P\ny")

        html = response.content.decode()
        self.assertIn("data-toast", html)
        self.assertIn("La note du 24 novembre 2025 est modifiée.", html)
        self.assertNotIn("<html", html)

    def test_messages_consommes_par_la_reponse(self):
        """Les toasts rendus dans la réponse ne reviennent pas à la page suivante."""
        self.post("# P\ny")

        page = self.client.get(reverse("note_taking:note_detail", args=["2025-11-24"]))
        self.assertNotIn("est modifiée", page.content.decode())

    def test_avertissement_d_un_titre_qui_saute_un_niveau(self):
        response = self.post("# P\n### Détail\ny")

        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("saute un niveau", html)

    def test_contenu_non_traitable_enregistre_avec_une_erreur(self):
        response = self.post("# P\n![a](absente.png)")

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "# P\n![a](absente.png)")
        self.assertEqual(response.status_code, 200)
        self.assertIn('role="alert"', response.content.decode())

    def test_formulaire_invalide_non_enregistre(self):
        """Bloc d'en-tête d'une autre date : rien n'est enregistré, l'erreur est
        dite dans un toast, avec un statut d'erreur pour le script."""
        response = self.post("---\ndate: 2025-11-25\n---\n# P\ny")

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "# P\nx")
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('role="alert"', html)
        self.assertIn("ne correspond pas à la date de la note", html)


class SaveInPlaceWithoutJavascriptTests(TestCase):
    """Sans JavaScript, « Enregistrer la note » revient à l'éditeur."""

    def test_modification_revient_a_l_editeur(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.post(
            edit_url("2025-11-24"),
            {"date": "2025-11-24", "body": "# P\ny", "stay": "1"},
        )

        self.assertRedirects(response, edit_url("2025-11-24"))

    def test_changement_de_date_mene_a_l_editeur_de_la_nouvelle_date(self):
        """Le script envoie normalement le formulaire quand la date change :
        l'adresse de l'éditeur change avec elle."""
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.post(
            edit_url("2025-11-24"),
            {"date": "2025-11-25", "body": "# P\nx", "stay": "1"},
        )

        self.assertRedirects(response, edit_url("2025-11-25"))

    def test_creation_mene_a_l_editeur(self):
        """Une nouvelle note enregistrée continue dans l'éditeur, pour que les
        enregistrements suivants se fassent sur place."""
        response = self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2025-11-24", "body": "# P\nx", "stay": "1"},
        )

        self.assertRedirects(response, edit_url("2025-11-24"))


class FinishEditingTests(TestCase):
    """Sans `stay`, l'enregistrement mène à la note, comme avant."""

    def test_modification_mene_a_la_note(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.post(
            edit_url("2025-11-24"), {"date": "2025-11-24", "body": "# P\ny"}
        )

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=["2025-11-24"])
        )


class EditorButtonsTests(TestCase):
    """L'en-tête de l'éditeur : « Enregistrer la note » (reste) et « Terminer
    l'édition » (mène à la note), tous deux reliés au formulaire."""

    def pages(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")
        return {
            "nouvelle note": self.client.get(reverse("note_taking:new_note")),
            "édition": self.client.get(edit_url("2025-11-24")),
        }

    def test_enregistrer_envoie_stay(self):
        for page, response in self.pages().items():
            with self.subTest(page=page):
                button = re.search(
                    r'<button[^>]*aria-label="Enregistrer la note"[^>]*>',
                    response.content.decode(),
                )
                assert button is not None
                self.assertIn('form="note-form"', button.group())
                self.assertIn('name="stay"', button.group())
                self.assertIn('value="1"', button.group())

    def test_terminer_l_edition(self):
        for page, response in self.pages().items():
            with self.subTest(page=page):
                button = re.search(
                    r"<button[^>]*aria-label=\"Terminer l(?:'|&#x27;)édition\"[^>]*>",
                    response.content.decode(),
                )
                assert button is not None
                self.assertIn('form="note-form"', button.group())
                self.assertNotIn("name=", button.group())

    def test_enregistrement_sur_place_seulement_a_l_edition(self):
        """Une nouvelle note n'existe pas encore : son premier enregistrement
        passe par la page suivante (l'éditeur)."""
        pages = self.pages()
        form = re.compile(r'<form id="note-form"[^>]*>')
        for page, expected in (("nouvelle note", False), ("édition", True)):
            with self.subTest(page=page):
                tag = form.search(pages[page].content.decode())
                assert tag is not None
                self.assertEqual("data-save-in-place" in tag.group(), expected)
