"""Ce que chaque app déclare à core dans son AppConfig, sans que core la connaisse.

- `home_link` : son entrée dans le menu de l'accueil général ;
- `project_usages` : ce qui, chez elle, utilise un projet (pour l'afficher et
  refuser la suppression d'un projet utilisé).

Les apps sont parcourues dans l'ordre d'INSTALLED_APPS.
"""

from dataclasses import dataclass

from django.apps import apps


@dataclass(frozen=True)
class HomeLink:
    url_name: str
    label: str
    icon: str


@dataclass(frozen=True)
class ProjectUsage:
    """Objets qui utilisent un projet, comptés par `lookup` depuis Project."""

    lookup: str
    singular: str
    plural: str

    def text(self, count: int) -> str:
        return f"{count} {self.singular if count == 1 else self.plural}"


def home_links() -> list[HomeLink]:
    links = (getattr(config, "home_link", None) for config in apps.get_app_configs())
    return [link for link in links if link]


def project_usages() -> list[ProjectUsage]:
    return [
        usage
        for config in apps.get_app_configs()
        for usage in getattr(config, "project_usages", ())
    ]
