"""Les résultats d'une recherche assemblés en un seul document Markdown (#356).

Les note parts trouvées sont remises bout à bout, avec leurs titres, pour s'afficher
comme une note (`render_note_part` : numéros des tableaux et figures calculés sur le
texte assemblé). **Sans accès à la base** : l'appelant (`search.py`) fournit des
`DocPart` déjà prêtes, avec leurs adresses.

Deux regroupements, au choix :

- `date` : un titre par note (`##`, avec un lien vers la note), les notes les plus
  récentes d'abord ; dessous, le projet (`###`) puis les niveaux, dans l'ordre où
  l'appelant a donné les note parts ;
- `path` : l'arbre Projet › niveaux (`##` pour le projet), trié sans casse ni
  accents ; sous chaque chemin, ses note parts de toutes les notes, la plus récente
  d'abord, chacune précédée de sa date en lien vers sa section.

Un titre déjà ouvert n'est pas répété : on n'écrit que les niveaux qui changent
depuis la note part précédente. Les niveaux vont de `##` à `######` ; au-delà, le
dernier niveau est gardé. Le `h1` reste celui de la page.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from core.tables import fold

from .qmd.parser import HEADING_SEPARATOR

GROUPS = ("date", "path")
MAX_LEVEL = 6


@dataclass(frozen=True)
class DocPart:
    date: date
    date_label: str
    # Adresse de la note, et de la section de cette note part dans la note.
    note_url: str
    part_url: str
    # Titres du projet au plus profond, tels qu'écrits.
    titles: tuple[str, ...]
    content: str
    project: str


def split_titles(heading_path: str) -> tuple[str, ...]:
    """Les titres d'un `heading_path` (« Projet › A › B »), du projet au plus profond."""
    if not heading_path:
        return ()
    return tuple(heading_path.split(HEADING_SEPARATOR))


def assemble(parts: Sequence[DocPart], group: str) -> str:
    """Le Markdown des note parts, regroupées par `group` (`date` ou `path`)."""
    if group == "date":
        return by_date(parts)
    if group == "path":
        return by_path(parts)
    raise ValueError(f"Regroupement inconnu : {group}")


def heading(level: int, text: str) -> str:
    return f"{'#' * min(level, MAX_LEVEL)} {text}"


def opened(
    previous: tuple[str, ...], titles: tuple[str, ...], first_level: int
) -> list[str]:
    """Les titres à écrire : ceux qui diffèrent de la note part précédente et leurs
    descendants. `first_level` : le niveau Markdown du premier titre."""
    common = 0
    while (
        common < len(previous)
        and common < len(titles)
        and previous[common] == titles[common]
    ):
        common += 1
    if titles and common == len(titles) and len(previous) > len(titles):
        # Retour à un niveau déjà ouvert plus haut : son titre est réécrit, sinon le
        # texte semblerait appartenir au dernier niveau écrit.
        common -= 1
    return [
        heading(first_level + depth, titles[depth])
        for depth in range(common, len(titles))
    ]


def by_date(parts: Sequence[DocPart]) -> str:
    notes: dict[date, list[DocPart]] = {}
    for item in parts:
        notes.setdefault(item.date, []).append(item)
    blocks: list[str] = []
    for day in sorted(notes, reverse=True):
        first = notes[day][0]
        blocks.append(heading(2, f"[Note du {first.date_label}]({first.note_url})"))
        previous: tuple[str, ...] = ()
        for item in notes[day]:
            blocks.extend(opened(previous, item.titles, 3))
            blocks.append(item.content)
            previous = item.titles
    return "\n\n".join(blocks) + "\n" if blocks else ""


def path_of(item: DocPart) -> tuple[str, ...]:
    return item.titles or (item.project,)


def by_path(parts: Sequence[DocPart]) -> str:
    order = sorted(
        enumerate(parts),
        key=lambda pair: (
            tuple(fold(title) for title in path_of(pair[1])),
            -pair[1].date.toordinal(),
            pair[0],
        ),
    )
    blocks: list[str] = []
    previous: tuple[str, ...] = ()
    for _, item in order:
        titles = path_of(item)
        blocks.extend(opened(previous, titles, 2))
        blocks.append(f"**[{item.date_label}]({item.part_url})**")
        blocks.append(item.content)
        previous = titles
    return "\n\n".join(blocks) + "\n" if blocks else ""
