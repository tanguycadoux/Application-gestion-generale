"""L'arbre des chemins d'un projet, avec ce qui l'utilise (#299).

Chaque app déclare ce qui, chez elle, utilise un niveau de chemin (`section_usages`
de son `AppConfig`) : `core` compte sans la connaître. Un niveau compte ce qui
l'utilise lui-même **et ses descendants** : on voit tout de suite si un niveau
sert, et à quoi.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse

from .app_registry import SectionUsage, section_usages
from .models import Project, Section
from .sections import similar_siblings


@dataclass(frozen=True)
class Similar:
    """Un niveau frère au nom proche (#374), et l'adresse du bilan qui réunit le
    niveau de la ligne avec lui (#373)."""

    name: str
    merge_url: str


@dataclass(frozen=True)
class UsageLink:
    """« 3 passages », et l'adresse de la page qui les liste (#375)."""

    text: str
    url: str


@dataclass
class TreeRow:
    section: Section
    depth: int
    # Ce qui utilise le niveau et ses descendants, par usage déclaré ; vide s'il est
    # inutilisé.
    usages: list[UsageLink] = field(default_factory=list)
    total: int = 0
    # Nombre de niveaux en dessous, à tous les niveaux.
    descendants: int = 0
    # Les frères qui ne diffèrent que par la casse, les accents, la ponctuation ou
    # un pluriel simple (#374).
    similar: list[Similar] = field(default_factory=list)

    @property
    def usage(self) -> str:
        """« 3 passages et 2 tâches », vide pour un niveau inutilisé."""
        return " et ".join(link.text for link in self.usages)

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


def usage_annotations(usages: list[SectionUsage]) -> dict[str, Count]:
    """`usage_0`, `usage_1`… : ce qui utilise le niveau lui-même, par usage déclaré
    (descendants exclus), à passer à `annotate`."""
    return {
        f"usage_{index}": Count(
            usage.lookup,
            distinct=True,
            filter=~usage.exclude if usage.exclude else Q(),
        )
        for index, usage in enumerate(usages)
    }


def section_counts(project: Project) -> dict[int, int]:
    """Par clé de niveau du projet, ce qui l'utilise lui-même, tous usages réunis :
    les compteurs de l'arbre de sa fiche (`core.path_tree`, #205)."""
    usages = section_usages()
    return {
        section.pk: sum(
            getattr(section, f"usage_{index}") for index in range(len(usages))
        )
        for section in Section.objects.filter(project=project).annotate(
            **usage_annotations(usages)
        )
    }


def section_tree(project: Project) -> list[TreeRow]:
    """Les niveaux du projet, parents d'abord, frères triés par nom."""
    usages = section_usages()
    sections = list(
        Section.objects.filter(project=project).annotate(**usage_annotations(usages))
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
        row = TreeRow(section, depth)
        rename_url = reverse("core:section_rename", args=[project.pk, section.pk])
        row.similar = [
            Similar(other.name, f"{rename_url}?{urlencode({'name': other.name})}")
            for other in similar_siblings(section, children[section.parent_id])
        ]
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
        row.usages = [
            UsageLink(usage.text(count), usage.url(section.pk))
            for usage, count in zip(usages, totals, strict=True)
            if count
        ]
        return totals

    for root in children.get(None, []):
        walk(root, 0)
    return rows
