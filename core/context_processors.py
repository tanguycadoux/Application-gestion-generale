"""Données communes à tous les gabarits."""

from django.urls import reverse

from .app_registry import header_templates, nav_sections, search_page


def navigation(request):
    """Les sections du menu commun, la barre de recherche et la droite de l'en-tête,
    déclarées par les apps (#232, #202, #386)."""
    page = search_page()
    return {
        "nav_sections": nav_sections(),
        "header_templates": header_templates(),
        "nav_search": {"url": reverse(page.url_name), "label": page.label}
        if page
        else None,
    }
