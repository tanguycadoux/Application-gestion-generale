"""Section « Debug » : galerie des alertes et analyse JSON, seulement en DEBUG (#235, #156)."""

import re

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from note_taking.models import Note

from .debug_urls import DebugUrlsTestCase

DEBUG_NAMES = (
    "core:alerts_gallery",
    "note_taking:debug_note_json",
)


class WithoutDebugTests(TestCase):
    def test_adresses_non_declarees(self):
        for name in DEBUG_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name)

    def test_adresses_de_debug_en_404(self):
        for path in (
            "/debug/alerts/",
            "/debug/notes/json/",
            "/debug/notes/2025-11-24/json/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_pas_de_section_debug_dans_le_menu(self):
        html = self.client.get("/").content.decode()

        self.assertNotIn("Debug", html)
        self.assertNotIn("Galerie des alertes", html)

    def test_vues_refusent_aussi_hors_debug(self):
        from django.http import Http404
        from django.test import RequestFactory

        from core.views import alerts_gallery

        with self.assertRaises(Http404):
            alerts_gallery(RequestFactory().get("/"))


class WithDebugTests(DebugUrlsTestCase):
    def test_galerie_des_alertes(self):
        response = self.client.get(reverse("core:alerts_gallery"))

        self.assertContains(response, "Galerie des alertes")
        self.assertContains(response, "/static/core/alerts_gallery.js")

    def test_un_toast_par_niveau_rendu_par_le_serveur(self):
        response = self.client.get(reverse("core:alerts_gallery"))

        self.assertContains(
            response, '<p class="flex-1">', count=5 + 2
        )  # + 2 modèles de base
        for text in (
            "Une information.",
            "Un point d&#x27;attention.",
            "Quelque chose a échoué.",
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'role="alert"', count=1 + 1)  # erreur + modèle

    def test_popover_de_confirmation_native(self):
        response = self.client.get(reverse("core:alerts_gallery"))

        self.assertContains(response, 'id="gallery-confirm" popover')
        self.assertContains(response, f'action="{reverse("core:alerts_gallery")}"')

    def test_confirmer_n_efface_rien_et_dit_le_succes(self):
        response = self.client.post(reverse("core:alerts_gallery"), follow=True)

        self.assertRedirects(response, reverse("core:alerts_gallery"))
        self.assertContains(
            response, "Confirmation reçue : rien n&#x27;a été supprimé."
        )

    def test_section_debug_en_dernier_dans_le_menu(self):
        html = self.client.get("/").content.decode()

        nav = re.search(r"<nav .*?</nav>", html, re.S).group()
        self.assertIn("Debug", nav)
        self.assertLess(nav.index("Projets"), nav.index("Debug"))
        for name in DEBUG_NAMES:
            self.assertIn(f'href="{reverse(name)}"', nav)

    def test_analyse_json_d_une_note(self):
        Note.objects.create(date="2025-11-24", body="# P\nx")

        response = self.client.get(
            reverse("note_taking:note_json", args=["2025-11-24"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("content", response.json())

    def test_choix_de_la_note_mene_a_son_analyse(self):
        page = self.client.get(reverse("note_taking:debug_note_json"))
        self.assertContains(page, 'type="date"')

        response = self.client.get(
            reverse("note_taking:debug_note_json"), {"date": "2025-11-24"}
        )

        self.assertRedirects(
            response,
            reverse("note_taking:note_json", args=["2025-11-24"]),
            fetch_redirect_response=False,
        )
