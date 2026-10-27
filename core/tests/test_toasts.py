"""Toasts des messages Django (#293) : rendus par le serveur, comme dans
research-paper-relationship-graph, le script n'ajoutant que le comportement.

Le projet n'a pas de lanceur de tests JavaScript : les tests du script le lisent.
"""

import re
from pathlib import Path
from typing import Any

from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.templatetags.ui import ALERT_VARIANTS


def read_static(name: str) -> str:
    path = finders.find(name)
    assert isinstance(path, str)
    return Path(path).read_text(encoding="utf-8")


def render_toast(level_tag: str, text: str = "Fait") -> str:
    message = type("Message", (), {"level_tag": level_tag, "__str__": lambda s: text})()
    return Template("{% load ui %}{% message_toast m %}").render(
        Context({"m": message})
    )


class MessageToastTests(SimpleTestCase):
    def test_variante_et_role_selon_le_niveau(self):
        cases = (
            ("error", "alert", "danger"),
            ("warning", "status", "warning"),
            ("success", "status", "success"),
            ("info", "status", "primary"),
            ("debug", "status", "secondary"),
        )
        for tag, role, variant in cases:
            with self.subTest(tag=tag):
                html = render_toast(tag)

                self.assertIn(f'role="{role}"', html)
                self.assertIn(ALERT_VARIANTS[variant], html)
                self.assertIn("pointer-events-auto shadow-lg", html)

    def test_seuls_succes_et_infos_disparaissent(self):
        for tag, autohide in (
            ("success", True),
            ("info", True),
            ("debug", True),
            ("warning", False),
            ("error", False),
        ):
            with self.subTest(tag=tag):
                self.assertEqual("data-toast-autohide" in render_toast(tag), autohide)

    def test_niveau_inconnu_traite_comme_une_info(self):
        self.assertIn(ALERT_VARIANTS["primary"], render_toast("autre"))

    def test_bouton_de_fermeture_cache_en_attendant_le_script(self):
        html = render_toast("info")

        self.assertIn('aria-label="Fermer la notification"', html)
        self.assertRegex(html, r"data-toast-close\s+hidden")

    def test_message_echappe(self):
        html = render_toast("success", "<b>gras</b> & « test »")

        self.assertIn("&lt;b&gt;gras&lt;/b&gt; &amp; « test »", html)
        self.assertNotIn("<b>", html)

    def test_icone_selon_la_variante(self):
        for tag in ("error", "warning", "success", "info"):
            with self.subTest(tag=tag):
                self.assertIn("<svg", render_toast(tag))


class ToastInPageTests(TestCase):
    def render_with_message(self, level: int, text: str) -> str:
        # Any : le stockage des messages est un attribut privé, absent du type.
        request: Any = RequestFactory().get("/")
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        messages.add_message(request, level, text)
        return render_to_string("base.html", request=request)

    def test_message_rendu_par_le_serveur(self):
        html = self.render_with_message(messages.SUCCESS, "Enregistré.")

        self.assertRegex(html, r'<div role="status"[^>]*data-toast')
        self.assertIn("Enregistré.", html)
        self.assertNotIn("Alert.toast", html)

    def test_conteneur_en_bas_a_droite(self):
        html = self.render_with_message(messages.INFO, "x")

        self.assertIn(
            '<div id="toasts" class="pointer-events-none fixed right-4 bottom-4 z-50'
            ' flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2">',
            html,
        )

    def test_le_script_est_charge(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertIn("core/toasts.js", html)
        self.assertIsNotNone(finders.find("core/toasts.js"))

    def test_modeles_pour_les_toasts_crees_par_les_scripts(self):
        html = self.client.get(reverse("core:index")).content.decode()

        for level, role in (("error", "alert"), ("success", "status")):
            with self.subTest(level=level):
                match = re.search(
                    rf'<template id="toast-template-{level}">(.*?)</template>',
                    html,
                    re.DOTALL,
                )
                assert match is not None
                self.assertIn(f'role="{role}"', match[1])

    def test_avertissement_d_un_import_sans_fichier(self):
        response = self.client.post(reverse("note_taking:import_files"), follow=True)

        self.assertContains(response, "Aucun fichier sélectionné.")
        self.assertRegex(response.content.decode(), r'role="status"[^>]*data-toast')
        self.assertNotContains(response, "data-toast-autohide\n")

    def test_message_de_succes_disparait_seul(self):
        response = self.client.post(
            reverse("core:project_create"),
            {"name": "Nouveau", "color": "teal"},
            follow=True,
        )

        self.assertContains(response, "data-toast-autohide")


class ToastScriptTests(SimpleTestCase):
    def setUp(self):
        self.script = read_static("core/toasts.js")

    def test_comportement_de_research_paper(self):
        self.assertIn("const AUTOHIDE_DELAY = 6000;", self.script)
        self.assertIn("[data-toast-close]", self.script)
        self.assertIn('event.key === "Escape"', self.script)
        for event in ("mouseenter", "mouseleave", "focusin", "focusout"):
            self.assertIn(f'"{event}"', self.script)
        self.assertIn('hasAttribute("data-toast-autohide")', self.script)

    def test_toast_cree_par_un_script_clone_le_modele(self):
        self.assertIn("window.Toast", self.script)
        self.assertIn("toast-template-", self.script)
        self.assertIn("textContent", self.script)

    def test_pas_d_insertion_en_html(self):
        """Un message s'affiche tel quel, sans être lu comme du HTML (#142)."""
        self.assertNotIn("innerHTML", self.script)
        self.assertNotIn("insertAdjacentHTML", self.script)

    def test_les_autres_scripts_utilisent_toast_show(self):
        for name in (
            "note_taking/editor.js",
            "note_taking/images_capture.js",
            "todolist/todo.js",
        ):
            with self.subTest(name=name):
                script = read_static(name)

                self.assertIn("Toast", script)
                self.assertNotIn("Alert.toast", script)
