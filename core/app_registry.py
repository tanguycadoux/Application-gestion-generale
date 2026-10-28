"""Ce que chaque app déclare à core dans son AppConfig, sans que core la connaisse.

- `nav_section` : sa section du menu commun (#232) ;
- `search_page` : sa page de recherche (un `NavItem`), vers laquelle mène la barre de
  recherche du menu commun (#202) ;
- `dashboard_blocks` : ses blocs de l'accueil général (#233) ;
- `debug_pages` : ses pages réservées au mode DEBUG, réunies dans la section
  « Debug » du menu (#235) ;
- `project_usages` : ce qui, chez elle, utilise un projet (pour l'afficher et
  refuser la suppression d'un projet utilisé) ;
- `section_usages` : ce qui, chez elle, utilise un niveau de chemin (compteurs de
  l'arbre des chemins, #299) ;
- `section_renamer` : comment elle renomme un niveau de chemin dans ses données
  (les titres des notes, #299).

Les apps sont parcourues dans l'ordre d'INSTALLED_APPS.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.db.models import Q


@dataclass(frozen=True)
class NavItem:
    """Une page du menu : nom d'URL, libellé et icône."""

    url_name: str
    label: str
    icon: str


@dataclass(frozen=True)
class NavSection:
    """Les pages d'une app dans le menu commun, sous son titre. `order` range les
    sections (Notes, Tâches, Projets) quel que soit l'ordre d'INSTALLED_APPS."""

    label: str
    order: int
    items: tuple[NavItem, ...]


@dataclass(frozen=True)
class DashboardBlock:
    """Un bloc de l'accueil général : un titre, un rang, un gabarit et la fonction
    qui lui donne son contexte. Le gabarit est rendu par `core`, qui ne sait rien
    de ce qu'il affiche."""

    title: str
    order: int
    template: str
    context: Callable[[], dict]


@dataclass(frozen=True)
class ProjectUsage:
    """Objets qui utilisent un projet, comptés par `lookup` depuis Project, sauf
    ceux qui répondent à `exclude` (tâches écartées, par exemple)."""

    lookup: str
    singular: str
    plural: str
    exclude: Q | None = None

    def text(self, count: int) -> str:
        return f"{count} {self.singular if count == 1 else self.plural}"


@dataclass(frozen=True)
class SectionUsage:
    """Objets qui utilisent un niveau de chemin, comptés par `lookup` depuis
    Section, sauf ceux qui répondent à `exclude` (tâches écartées)."""

    lookup: str
    singular: str
    plural: str
    exclude: Q | None = None

    def text(self, count: int) -> str:
        return f"{count} {self.singular if count == 1 else self.plural}"


@dataclass(frozen=True)
class HeadingOccurrence:
    """Un endroit où le nom d'un niveau est écrit, pour le bilan d'un renommage :
    `key` identifie la case à cocher, `where` dit où (« Note du 24 novembre,
    ligne 5 »), `url` y mène et `chain` donne le chemin entier."""

    key: str
    where: str
    url: str
    chain: str


@dataclass(frozen=True)
class SectionRenamer:
    """Comment une app renomme un niveau de chemin : `occurrences(projet, niveaux)`
    liste ce qu'elle réécrirait ; `rename(projet, niveaux, nouveau nom, clés)`
    réécrit celles qui sont choisies et renvoie les phrases du compte rendu."""

    occurrences: Callable[..., list[HeadingOccurrence]]
    rename: Callable[..., list[str]]


DEBUG_SECTION_ORDER = 90


def nav_sections() -> list[NavSection]:
    """Les sections du menu, rangées par `order`. Avec `DEBUG = True` seulement, une
    dernière section « Debug » réunit les `debug_pages` des apps (#235)."""
    sections = [
        section
        for config in apps.get_app_configs()
        if (section := getattr(config, "nav_section", None))
    ]
    if settings.DEBUG:
        pages = tuple(
            page
            for config in apps.get_app_configs()
            for page in getattr(config, "debug_pages", ())
        )
        if pages:
            sections.append(NavSection("Debug", DEBUG_SECTION_ORDER, pages))
    return sorted(sections, key=lambda section: section.order)


def search_page() -> NavItem | None:
    """La page de recherche déclarée par une app (la première), pour la barre du menu."""
    for config in apps.get_app_configs():
        if page := getattr(config, "search_page", None):
            return page
    return None


def dashboard_blocks() -> list[DashboardBlock]:
    blocks = (
        block
        for config in apps.get_app_configs()
        for block in getattr(config, "dashboard_blocks", ())
    )
    return sorted(blocks, key=lambda block: block.order)


def project_usages() -> list[ProjectUsage]:
    return [
        usage
        for config in apps.get_app_configs()
        for usage in getattr(config, "project_usages", ())
    ]


def section_usages() -> list[SectionUsage]:
    return [
        usage
        for config in apps.get_app_configs()
        for usage in getattr(config, "section_usages", ())
    ]


def section_renamers() -> list[SectionRenamer]:
    renamers = (
        getattr(config, "section_renamer", None) for config in apps.get_app_configs()
    )
    return [renamer for renamer in renamers if renamer]
