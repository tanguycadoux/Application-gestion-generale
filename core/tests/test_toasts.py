"""Tests des toasts : le niveau du message Django est transmis au toast (#120)."""

import unittest

from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse


class ToastLevelTests(TestCase):
    def render_with_message(self, level: int, text: str) -> str:
        request = RequestFactory().get("/")
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        messages.add_message(request, level, text)
        return render_to_string("base.html", request=request)

    @unittest.expectedFailure
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

    @unittest.expectedFailure
    def test_avertissement_d_un_import_sans_fichier(self):
        response = self.client.post(reverse("note_taking:import_files"), follow=True)

        self.assertContains(response, '{ type: "warning" }')
