"""Ce que chaque app déclare à core dans son AppConfig, sans que core la connaisse.

- `nav_section` : sa section du menu commun (#232) ;
- `search_page` : sa page de recherche (un `NavItem`), vers laquelle mène la barre de
  recherche du menu commun (#202) ;
- `header_templates` : ses gabarits à droite de l'en-tête de toutes les pages (#386) ;
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
from django.urls import reverse
from django.utils.text import Truncator

# Les tâches citées sous un titre, dans le bilan d'un renommage (#376).
TASKS_SHOWN = 3
TASK_TITLE_LENGTH = 60


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
    Section, sauf ceux qui répondent à `exclude` (tâches écartées).

    `url_name` et `query` (« subjects={pk} ») donnent la page qui les liste, filtrée
    sur un niveau, descendants compris : elle doit montrer ce qui est compté (#375)."""

    lookup: str
    singular: str
    plural: str
    url_name: str
    query: str
    exclude: Q | None = None

    def url(self, section_pk: int) -> str:
        return f"{reverse(self.url_name)}?{self.query.format(pk=section_pk)}"

    def text(self, count: int) -> str:
        return f"{count} {self.singular if count == 1 else self.plural}"


@dataclass(frozen=True)
class HeadingOccurrence:
    """Un endroit où le nom d'un niveau est écrit, pour le bilan d'un renommage :
    `key` identifie la case à cocher, `where` dit où (« Note du 24 novembre,
    ligne 5 »), `url` y mène et `chain` donne le chemin entier. `excerpt` (les premiers
    mots de la section) et `tasks` (les titres de ses tâches) aident à choisir (#376)."""

    key: str
    where: str
    url: str
    chain: str
    excerpt: str = ""
    tasks: tuple[str, ...] = ()

    @property
    def tasks_text(self) -> str:
        """« 2 tâches : Commander le béton, Relancer », les trois premières ; vide
        sans tâche."""
        if not self.tasks:
            return ""
        shown = [
            Truncator(t).chars(TASK_TITLE_LENGTH) for t in self.tasks[:TASKS_SHOWN]
        ]
        more = len(self.tasks) - len(shown)
        others = f" et {more} autre{'s' if more > 1 else ''}" if more else ""
        noun = "tâche" if len(self.tasks) == 1 else "tâches"
        return f"{len(self.tasks)} {noun}\u00a0: {', '.join(shown)}{others}"


@dataclass(frozen=True)
class SectionRenamer:
    """Comment une app renomme un niveau de chemin : `occurrences(projet, niveaux)`
    liste ce qu'elle réécrirait ; `rename(projet, niveaux, nouveau nom, clés)`
    réécrit celles qui sont choisies et renvoie les phrases du compte rendu."""

    occurrences: Callable[..., list[HeadingOccurrence]]
    rename: Callable[..., list[str]]


@dataclass(frozen=True)
class ProjectRenamer:
    """Comment une app renomme un projet (#170) : `occurrences(projet)` liste ses
    titres `#` écrits dans les notes, pour le bilan ; `rename(projet, ancien nom,
    nouveau nom)` les réécrit tous et renvoie les phrases du compte rendu. Le projet
    est déjà renommé en base quand `rename` est appelé."""

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


def header_templates() -> list[str]:
    """Les gabarits que les apps placent à droite de l'en-tête (#355, #386)."""
    return [
        template
        for config in apps.get_app_configs()
        for template in getattr(config, "header_templates", ())
    ]


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


def project_renamers() -> list[ProjectRenamer]:
    renamers = (
        getattr(config, "project_renamer", None) for config in apps.get_app_configs()
    )
    return [renamer for renamer in renamers if renamer]
