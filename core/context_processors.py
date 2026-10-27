"""Données communes à tous les gabarits."""

from .app_registry import nav_sections


def navigation(request):
    """Les sections du menu commun, déclarées par les apps (#232)."""
    return {"nav_sections": nav_sections()}
