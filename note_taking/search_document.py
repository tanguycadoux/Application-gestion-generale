"""Les résultats d'une recherche assemblés en un seul document Markdown (#356).

Les note parts trouvées sont remises bout à bout, avec leurs titres, pour s'afficher
comme une note (`render_note_part` : numéros des tableaux et figures calculés sur le
texte assemblé). **Sans accès à la base** : l'appelant (`search.py`) fournit des
`DocPart` déjà prêtes, avec leurs adresses.

Les titres sont ceux des **niveaux en base** (#369) : le projet, puis la section de
la note part et ses ancêtres, chacun sous son nom en base. Deux niveaux sont le même
s'ils ont la même identité (`Level.key`), quelle que soit l'écriture des titres dans
les notes (« Réunion de Chantier », « Réunion  de chantier ») ; deux niveaux distincts
ne sont jamais confondus, même si leurs noms ne diffèrent que par la casse ou les
accents (projets « Chantier Nord » et « Chantier nord »).

Deux regroupements, au choix :

- `date` : un titre par note (`##`, avec un lien vers la note), les notes les plus
  récentes d'abord ; dessous, le projet (`###`) puis les niveaux, dans l'ordre où
  l'appelant a donné les note parts ;
- `path` : l'arbre Projet › niveaux (`##` pour le projet), trié sans casse ni
  accents, puis par identité à nom égal : un niveau et ses descendants se suivent,
  sans s'entrelacer avec un autre ; sous chaque niveau, ses note parts de toutes les
  notes, la plus récente d'abord, chacune précédée de sa date en lien vers sa section.

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
class Level:
    """Un niveau du document : son identité (la clé du projet pour le premier niveau,
    celle de la section ensuite) et son nom en base."""

    key: int
    name: str


@dataclass(frozen=True)
class DocPart:
    date: date
    date_label: str
    # Adresse de la note, et de la section de cette note part dans la note.
    note_url: str
    part_url: str
    # Niveaux du projet au plus profond.
    levels: tuple[Level, ...]
    content: str


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
    previous: tuple[Level, ...], levels: tuple[Level, ...], first_level: int
) -> list[str]:
    """Les titres à écrire : les niveaux qui diffèrent (par leur identité) de ceux de
    la note part précédente, et leurs descendants. `first_level` : le niveau Markdown
    du premier titre."""
    common = 0
    while (
        common < len(previous)
        and common < len(levels)
        and previous[common].key == levels[common].key
    ):
        common += 1
    if levels and common == len(levels) and len(previous) > len(levels):
        # Retour à un niveau déjà ouvert plus haut : son titre est réécrit, sinon le
        # texte semblerait appartenir au dernier niveau écrit.
        common -= 1
    return [
        heading(first_level + depth, levels[depth].name)
        for depth in range(common, len(levels))
    ]


def by_date(parts: Sequence[DocPart]) -> str:
    notes: dict[date, list[DocPart]] = {}
    for item in parts:
        notes.setdefault(item.date, []).append(item)
    blocks: list[str] = []
    for day in sorted(notes, reverse=True):
        first = notes[day][0]
        blocks.append(heading(2, f"[Note du {first.date_label}]({first.note_url})"))
        previous: tuple[Level, ...] = ()
        for item in notes[day]:
            blocks.extend(opened(previous, item.levels, 3))
            blocks.append(item.content)
            previous = item.levels
    return "\n\n".join(blocks) + "\n" if blocks else ""


def tree_order(levels: tuple[Level, ...]) -> tuple[tuple[str, int], ...]:
    """La place d'un chemin dans l'arbre : chaque niveau sans casse ni accents, puis
    par identité à nom égal. La clé d'un niveau ne dépend que de lui : un niveau et
    ses descendants se suivent, et deux niveaux distincts ne s'entrelacent pas."""
    return tuple((fold(level.name), level.key) for level in levels)


def by_path(parts: Sequence[DocPart]) -> str:
    order = sorted(
        enumerate(parts),
        key=lambda pair: (
            tree_order(pair[1].levels),
            -pair[1].date.toordinal(),
            pair[0],
        ),
    )
    blocks: list[str] = []
    previous: tuple[Level, ...] = ()
    for _, item in order:
        blocks.extend(opened(previous, item.levels, 2))
        blocks.append(f"**[{item.date_label}]({item.part_url})**")
        blocks.append(item.content)
        previous = item.levels
    return "\n\n".join(blocks) + "\n" if blocks else ""
