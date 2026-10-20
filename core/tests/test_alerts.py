"""Tests des alertes : toasts des messages Django et popover de confirmation.

Le projet n'a pas de lanceur de tests JavaScript : les tests du script le lisent.
"""

import json
import re
from pathlib import Path
from typing import Any

from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.templatetags.ui import BUTTON_VARIANTS

SHAPE = "rounded-xl border border-slate-200 bg-white p-3 shadow-lg"

TOAST_TYPES = {
    "info": ("info", "border-l-blue-700", "text-blue-800", "bg-blue-500"),
    "success": ("check_circle", "border-l-green-700", "text-green-800", "bg-green-500"),
    "warning": ("warning", "border-l-amber-500", "text-amber-800", "bg-amber-400"),
    "error": ("error", "border-l-red-700", "text-red-800", "bg-red-500"),
}


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


class ToastLevelTests(TestCase):
    """Le niveau du message Django est transmis au toast (#120)."""

    def render_with_message(self, level: int, text: str) -> str:
        # Any : le stockage des messages est un attribut privé, absent du type.
        request: Any = RequestFactory().get("/")
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        messages.add_message(request, level, text)
        return render_to_string("base.html", request=request)

    def test_type_du_toast_selon_le_niveau(self):
        levels = {
            messages.INFO: "info",
            messages.SUCCESS: "success",
            messages.WARNING: "warning",
            messages.ERROR: "error",
        }
        for level, toast_type in levels.items():
            with self.subTest(toast_type=toast_type):
                html = self.render_with_message(level, "Message")

                self.assertIn(
                    f'Alert.toast("Message", {{ type: "{toast_type}" }});', html
                )

    def test_avertissement_d_un_import_sans_fichier(self):
        response = self.client.post(reverse("note_taking:import_files"), follow=True)

        self.assertContains(response, '{ type: "warning" }')


class AlertTextTests(SimpleTestCase):
    """Les textes s'affichent tels quels, sans être lus comme du HTML (#142)."""

    def setUp(self):
        self.script = read_static("core/alert_system.js")

    def test_pas_d_insertion_en_html(self):
        self.assertNotIn("innerHTML", self.script)
        self.assertNotIn("insertAdjacentHTML", self.script)

    def test_textes_places_en_texte(self):
        self.assertIn("textContent", self.script)

    def test_pas_de_texte_dans_un_gabarit_de_chaine(self):
        """Message, titre et libellés ne passent pas par une chaîne `${…}` en HTML."""
        interpolations = [i.strip() for i in re.findall(r"\$\{([^}]*)\}", self.script)]

        for name in ("message", "title", "ok_label", "cancel_label"):
            with self.subTest(name=name):
                self.assertNotIn(name, interpolations)


class AlertStyleTests(TestCase):
    """Toasts et popover cohérents avec l'interface (#154)."""

    def setUp(self):
        self.script = read_static("core/alert_system.js")

    def test_classes_des_boutons_transmises_aux_scripts(self):
        html = self.client.get("/").content.decode()

        match = re.search(
            r'<script id="button-variants" type="application/json">(.*?)</script>',
            html,
        )
        assert match is not None
        self.assertEqual(json.loads(match.group(1)), BUTTON_VARIANTS)
        self.assertLess(
            html.index('id="button-variants"'), html.index("core/alert_system.js")
        )

    def test_forme_commune(self):
        """Une seule définition, utilisée par le toast et par la popover."""
        self.assertIn(f'const ALERT_SHAPE = "{SHAPE}";', self.script)
        self.assertGreaterEqual(self.script.count("${ALERT_SHAPE}"), 2)

    def test_toasts_par_type(self):
        for toast_type, classes in TOAST_TYPES.items():
            with self.subTest(toast_type=toast_type):
                for value in classes:
                    self.assertIn(f'"{value}"', self.script)
        self.assertIn("border-l-4", self.script)

    def test_boutons_de_la_popover_selon_les_variantes(self):
        self.assertIn('getElementById("button-variants")', self.script)
        self.assertLess(
            self.script.index("variants.ghost"), self.script.index("variants.danger")
        )


class AlertStylesheetTests(SimpleTestCase):
    """La feuille ne garde que les animations, dont la barre de progression.

    La version navigateur de Tailwind génère les classes d'un élément ajouté par
    script après coup : une largeur de départ lue sur `w-full` valait 0 (#154).
    La barre est donc animée par la feuille, chargée au départ.
    """

    def test_feuille_reduite_aux_animations(self):
        css = read_static("core/alert_system.css")

        self.assertNotRegex(css, r"\b(?:color|background|border|box-shadow)\s*:")
        self.assertIn(".alert__toast-progress {", css)
        self.assertIn("@keyframes alert-toast-progress", css)

    def test_script_ne_donne_que_la_duree_de_la_barre(self):
        script = read_static("core/alert_system.js")

        self.assertIn("style.animationDuration", script)
        self.assertNotIn("offsetWidth", script)
