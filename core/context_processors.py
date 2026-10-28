"""Données communes à tous les gabarits."""

from django.urls import reverse

from .app_registry import nav_sections, search_page


def navigation(request):
    """Les sections du menu commun et la barre de recherche, déclarées par les apps
    (#232, #202)."""
    page = search_page()
    return {
        "nav_sections": nav_sections(),
        "nav_search": {"url": reverse(page.url_name), "label": page.label}
        if page
        else None,
    }
