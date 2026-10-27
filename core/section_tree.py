"""L'arbre des chemins d'un projet, avec ce qui l'utilise (#299).

Chaque app déclare ce qui, chez elle, utilise un niveau de chemin (`section_usages`
de son `AppConfig`) : `core` compte sans la connaître. Un niveau compte ce qui
l'utilise lui-même **et ses descendants** : on voit tout de suite si un niveau
sert, et à quoi.
"""

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Count, Q

from .app_registry import section_usages
from .models import Project, Section


@dataclass
class TreeRow:
    section: Section
    depth: int
    # « 3 note parts et 2 tâches », vide si rien n'utilise ce niveau ni ses
    # descendants.
    usage: str
    total: int
    # Nombre de niveaux en dessous, à tous les niveaux.
    descendants: int = 0

    @property
    def usage_id(self) -> str:
        return f"niveau-{self.section.pk}-usage"

    @property
    def delete_confirm(self) -> str:
        """Texte de la confirmation : le niveau et ce qui disparaît avec lui."""
        below = ""
        if self.descendants == 1:
            below = " et son sous-niveau"
        elif self.descendants:
            below = f" et ses {self.descendants} sous-niveaux"
        return f"Supprimer définitivement le niveau{below} ?"


def section_tree(project: Project) -> list[TreeRow]:
    """Les niveaux du projet, parents d'abord, frères triés par nom."""
    usages = section_usages()
    sections = list(
        Section.objects.filter(project=project).annotate(
            **{
                f"usage_{index}": Count(
                    usage.lookup,
                    distinct=True,
                    filter=~usage.exclude if usage.exclude else Q(),
                )
                for index, usage in enumerate(usages)
            }
        )
    )
    children: dict[int | None, list[Section]] = defaultdict(list)
    for section in sections:
        children[section.parent_id].append(section)
    for siblings in children.values():
        siblings.sort(key=lambda section: section.name.casefold())

    rows: list[TreeRow] = []

    def walk(section: Section, depth: int) -> list[int]:
        """Ajoute la ligne de ce niveau, puis celles de ses descendants ; renvoie ce
        qui utilise le niveau et ses descendants, par usage."""
        row = TreeRow(section, depth, "", 0)
        rows.append(row)
        index = len(rows)
        totals = [getattr(section, f"usage_{index}") for index in range(len(usages))]
        for child in children.get(section.pk, []):
            totals = [
                total + more
                for total, more in zip(totals, walk(child, depth + 1), strict=True)
            ]
        row.descendants = len(rows) - index
        row.total = sum(totals)
        row.usage = " et ".join(
            usage.text(count)
            for usage, count in zip(usages, totals, strict=True)
            if count
        )
        return totals

    for root in children.get(None, []):
        walk(root, 0)
    return rows
