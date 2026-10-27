"""Tests des pages réservées au mode DEBUG (#235).

Les adresses de développement ne sont déclarées qu'avec `DEBUG = True`, au chargement
des modules d'adresses ; le lanceur de tests force `DEBUG = False`. `DebugUrlsTestCase`
l'active le temps de la classe et recharge les adresses, puis remet l'état d'origine.
"""

import importlib
import sys

from django.test import TestCase, override_settings
from django.urls import clear_url_caches, set_urlconf

URL_MODULES = ("core.urls", "note_taking.urls", "todolist.urls", "app_gestion.urls")


def reload_urls() -> None:
    for name in URL_MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    clear_url_caches()
    set_urlconf(None)


class DebugUrlsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        override = override_settings(DEBUG=True)
        override.enable()
        reload_urls()

        def restore():
            override.disable()
            reload_urls()

        cls.addClassCleanup(restore)
