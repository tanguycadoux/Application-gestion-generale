"""Ce que chaque app déclare à core dans son AppConfig, sans que core la connaisse.

- `home_link` : son entrée dans le menu de l'accueil général ;
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
from django.db.models import Q


@dataclass(frozen=True)
class HomeLink:
    url_name: str
    label: str
    icon: str


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


def home_links() -> list[HomeLink]:
    links = (getattr(config, "home_link", None) for config in apps.get_app_configs())
    return [link for link in links if link]


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
