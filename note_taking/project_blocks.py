"""Blocs des notes dans la fiche d'un projet (#205) : ses passages et ses images."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

from django.urls import reverse

from core.app_registry import ProjectScope
from core.sections import path_labels
from core.tables import fold
from images.models import Image

from .excerpts import first_words
from .models import Passage
from .search_document import GROUPS

# Les passages les plus récents d'abord, comme la recherche et la liste des notes ;
# `asc` les remet dans l'ordre chronologique.
ORDERS = ("desc", "asc")


@dataclass
class PassageItem:
    date: date
    # Adresse du titre du passage dans sa note.
    url: str
    # Chemin sous le projet, vide pour le texte placé directement sous lui.
    path: str
    excerpt: str


@dataclass
class PassageGroup:
    """Les passages d'une note (`date`) ou d'un niveau (`path`)."""

    date: date | None = None
    path: str = ""
    items: list[PassageItem] = field(default_factory=list)


def option(params: Mapping[str, str], name: str, choices: tuple[str, ...]) -> str:
    """La valeur d'une option de l'adresse ; la première si absente ou inconnue."""
    value = params.get(name, choices[0])
    return value if value in choices else choices[0]


def passages_of(scope: ProjectScope):
    return Passage.objects.filter(scope.lookup)


def notes_block(scope: ProjectScope) -> dict:
    """Les passages du projet ou du niveau choisi, par note ou par chemin, chacun avec
    ses premiers mots ; le texte entier se lit dans la vue « Document » de la
    recherche. Deux requêtes, quel que soit leur nombre."""
    group = option(scope.params, "group", GROUPS)
    order = option(scope.params, "order", ORDERS)
    day = "note__date" if order == "asc" else "-note__date"
    passages = passages_of(scope).select_related("note").order_by(day, "position")
    labels = path_labels(with_project=False)
    items = [
        PassageItem(
            passage.note.date,
            reverse("note_taking:note_detail", args=[passage.note.date])
            + (f"#{passage.heading_id}" if passage.heading_id else ""),
            labels.get(passage.section_id or 0, ""),
            first_words(passage.content.split("\n")),
        )
        for passage in passages
    ]
    target = (
        {"subjects": scope.section.pk}
        if scope.section
        else {"projects": scope.project.pk}
    )
    query = urlencode({**target, "view": "document", "group": group})
    return {
        "groups": by_path(items) if group == "path" else by_date(items),
        "group": group,
        "order": order,
        "total": len(items),
        "document_url": f"{reverse('note_taking:notes_search')}?{query}",
    }


def by_date(items: list[PassageItem]) -> list[PassageGroup]:
    groups: dict[date, PassageGroup] = {}
    for item in items:
        groups.setdefault(item.date, PassageGroup(date=item.date)).items.append(item)
    return list(groups.values())


def by_path(items: list[PassageItem]) -> list[PassageGroup]:
    """Un groupe par niveau, triés par chemin ; le texte sans chemin d'abord."""
    groups: dict[str, PassageGroup] = {}
    for item in items:
        groups.setdefault(item.path, PassageGroup(path=item.path)).items.append(item)
    return sorted(groups.values(), key=lambda group: fold(group.path))


def images_block(scope: ProjectScope) -> dict | None:
    """Les images des passages, une fois chacune ; pas de bloc sans image."""
    images = list(Image.objects.filter(passages__in=passages_of(scope)).distinct())
    return {"images": images} if images else None
