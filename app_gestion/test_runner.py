"""Lanceur de tests sans réseau (#218)."""

from unittest.mock import patch

from django.test.runner import DiscoverRunner


class NoNetworkTestRunner(DiscoverRunner):
    """Toute connexion réseau échoue pendant les tests : l'application ne fait
    aucune requête vers l'extérieur, et un téléchargement (add_icon) se simule."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._network_guard = patch(
            "socket.socket.connect",
            side_effect=RuntimeError(
                "Accès au réseau interdit pendant les tests : simuler la requête."
            ),
        )
        self._network_guard.start()

    def teardown_test_environment(self, **kwargs):
        self._network_guard.stop()
        super().teardown_test_environment(**kwargs)
