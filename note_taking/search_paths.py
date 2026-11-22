"""Les niveaux de `chemin:` (#365, #368) : lesquels une valeur désigne, et que
proposer quand elle n'en désigne aucun.

- `chemin:Réunion/Préparation` désigne le niveau « Préparation » directement sous
  « Réunion », à n'importe quelle profondeur et dans n'importe quel projet ; les
  niveaux écrits se suivent sans trou. Les noms se comparent à leur forme réduite
  (#372), sans casse ni accents.
- `chemin:réunion*` : le dernier niveau est un préfixe, comme `mot*` dans le texte :
  un mot de son nom commence par lui (sans casse ni accents, sans forme réduite).
- `path_reports` dit, pour chaque `chemin:` de la requête, les niveaux retenus ; s'il
  n'y en a aucun, des requêtes à essayer (#368), qui ne sont **que proposées** : un
  chemin est un filtre, l'élargir sans le dire mélangerait des branches.
"""

import re
from dataclasses import dataclass, field
from functools import cached_property

from core.models import Project, Section
from core.sections import (
    INPUT_SEPARATOR,
    LABEL_SEPARATOR,
    split_path,
    with_descendants,
)
from core.tables import fold

from .search_index import edit_distance, tolerated_typos
from .search_query import OPERATORS, Token, fold_name, read_tokens
from .word_forms import reduce_text

PREFIX_MARK = "*"
# Un nom partiel n'est proposé qu'à partir de CONTAINS_MIN_LENGTH lettres : « de »
# est dans presque tous les noms.
CONTAINS_MIN_LENGTH = 3
MAX_SUGGESTIONS = 5


@dataclass(frozen=True)
class PathPattern:
    """Une valeur de `chemin:` lue : ses niveaux à leur forme réduite, et si le dernier
    est un préfixe (alors replié sans forme réduite, comme un préfixe du texte)."""

    levels: tuple[str, ...]
    prefix: bool = False

    def __bool__(self) -> bool:
        return bool(self.levels)


def read_path(value: str) -> PathPattern:
    levels = split_path(value)
    prefix = bool(levels) and levels[-1].endswith(PREFIX_MARK)
    if prefix:
        last = levels[-1].rstrip(PREFIX_MARK).strip()
        levels = [*levels[:-1], last] if last else levels[:-1]
    if not levels:
        return PathPattern(())
    reduced = [reduce_text(level) for level in levels]
    if prefix:
        reduced[-1] = fold(levels[-1])
    return PathPattern(tuple(reduced), prefix)


def starts_a_word(prefix: str, name: str) -> bool:
    """`prefix` commence un mot de `name` (tous deux repliés)."""
    return re.search(rf"(?<!\w){re.escape(prefix)}", name) is not None


class Levels:
    """Tous les niveaux, lus une fois, et leur chemin sous leur projet."""

    def __init__(self) -> None:
        rows = list(
            Section.objects.values_list("pk", "parent_id", "project_id", "name")
        )
        self.parent = {pk: parent for pk, parent, _, _ in rows}
        self.project = {pk: project for pk, _, project, _ in rows}
        self.name = {pk: name for pk, _, _, name in rows}
        self.pks = [pk for pk, _, _, _ in rows]

    @cached_property
    def project_names(self) -> dict[int, str]:
        return dict(Project.objects.values_list("pk", "name"))

    def chain(self, pk: int) -> list[int]:
        """Le niveau et ses ancêtres, de la racine vers lui."""
        chain: list[int] = []
        current: int | None = pk
        while current is not None:
            chain.insert(0, current)
            current = self.parent[current]
        return chain

    @cached_property
    def reduced(self) -> dict[int, str]:
        return {pk: reduce_text(name) for pk, name in self.name.items()}

    @cached_property
    def folded(self) -> dict[int, str]:
        return {pk: fold(name) for pk, name in self.name.items()}

    def matches(self, pk: int, pattern: PathPattern) -> bool:
        """Le chemin du niveau finit par les niveaux écrits."""
        chain = self.chain(pk)
        size = len(pattern.levels)
        if len(chain) < size:
            return False
        tail = chain[-size:]
        exact = pattern.levels[:-1] if pattern.prefix else pattern.levels
        if any(
            self.reduced[pk] != level for pk, level in zip(tail, exact, strict=False)
        ):
            return False
        return not pattern.prefix or starts_a_word(
            pattern.levels[-1], self.folded[tail[-1]]
        )

    def matching(self, pattern: PathPattern) -> list[int]:
        if not pattern:
            return []
        return [pk for pk in self.pks if self.matches(pk, pattern)]

    def label(self, pk: int) -> str:
        """« Projet › Réunion › Préparation »."""
        names = [self.name[level] for level in self.chain(pk)]
        return LABEL_SEPARATOR.join([self.project_names[self.project[pk]], *names])


def section_ids_at(paths: list[str]) -> set[int]:
    """Les niveaux que désignent ces valeurs de `chemin:`, et leurs descendants.

    « A/B » trouve A/B, A/B/C et C/A/B, pas A/C/B ; `projet:` restreint à un projet.
    Les noms se comparent à leur forme réduite : « Calcul thermique » trouve
    « Calculs thermiques » (#372).
    """
    levels = Levels()
    found: set[int] = set()
    for path in paths:
        found.update(levels.matching(read_path(path)))
    return with_descendants(found)


@dataclass(frozen=True)
class Suggestion:
    """Une requête à essayer : `q` la requête entière, `label` la partie changée."""

    q: str
    label: str


@dataclass
class PathReport:
    """Un `chemin:` de la requête : la valeur écrite et les niveaux qu'elle désigne
    (« Projet › A › B »), ou, si elle n'en désigne aucun, des requêtes à essayer."""

    written: str
    negated: bool
    levels: list[str] = field(default_factory=list)
    # Les niveaux retenus eux-mêmes, sans descendants : marqués dans l'arbre (#380).
    section_ids: list[int] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def single_level(self) -> bool:
        return len(split_path(self.written)) <= 1


def path_reports(text: str | None) -> list[PathReport]:
    """Un bilan par `chemin:` (ou `-chemin:`) non vide de la requête, dans l'ordre."""
    tokens = read_tokens(text or "")
    found = [
        index
        for index, token in enumerate(tokens)
        if token.name
        and OPERATORS.get(fold_name(token.name)) == "paths"
        and read_path(token.value.strip())
    ]
    if not found:
        return []
    levels = Levels()
    reports = []
    for index in found:
        token = tokens[index]
        report = PathReport(token.value.strip(), token.negated)
        retained = levels.matching(read_path(report.written))
        report.section_ids = retained
        report.levels = sorted(
            (levels.label(pk) for pk in retained), key=lambda label: fold(label)
        )
        if not retained:
            report.suggestions = suggest(tokens, index, levels)
        reports.append(report)
    return reports


def suggest(tokens: list[Token], index: int, levels: Levels) -> list[Suggestion]:
    """Les requêtes à essayer pour un `chemin:` sans niveau, dans cet ordre :
    les guillemets oubliés (seuls proposés s'ils suffisent), le projet écrit en
    premier niveau, puis les niveaux de nom proche (nom partiel ou fautes)."""
    token = tokens[index]
    completed = complete_quotes(tokens, index, levels)
    if completed:
        return [completed]
    found: list[Suggestion] = []
    project_first = read_project_first(tokens, index, levels)
    if project_first:
        found.append(project_first)
    seen: set[str] = set()
    for written in close_paths(split_path(token.value.strip()), levels):
        # Un guillemet ne s'écrit pas dans une valeur : pas de suggestion.
        if fold(written) in seen or '"' in written:
            continue
        seen.add(fold(written))
        raw = operator_text(token, written)
        found.append(Suggestion(rewrite(tokens, index, index + 1, raw), raw))
    return found[:MAX_SUGGESTIONS]


def complete_quotes(
    tokens: list[Token], index: int, levels: Levels
) -> Suggestion | None:
    """`chemin:réunion de chantier` : si les mots qui suivent complètent un nom de
    niveau, la même valeur entre guillemets. La plus longue d'abord."""
    token = tokens[index]
    if token.quoted:
        return None
    end = index + 1
    while end < len(tokens) and is_plain_word(tokens[end]):
        end += 1
    for stop in range(end, index + 1, -1):
        value = " ".join([token.value, *(t.value for t in tokens[index + 1 : stop])])
        if levels.matching(read_path(value)):
            raw = operator_text(token, value)
            return Suggestion(rewrite(tokens, index, stop, raw), raw)
    return None


def is_plain_word(token: Token) -> bool:
    return not (token.name or token.negated or token.quoted)


def read_project_first(
    tokens: list[Token], index: int, levels: Levels
) -> Suggestion | None:
    """`chemin:"Chantier Nord/Réunion"` : le premier niveau est un projet, proposé en
    `projet:` suivi du reste. Pas pour une exclusion : `-projet:A -chemin:B` exclut
    tout A et tout B, pas « A › B »."""
    token = tokens[index]
    written = split_path(token.value.strip())
    if token.negated or not written:
        return None
    project = next(
        (
            (pk, name)
            for pk, name in levels.project_names.items()
            if fold(name) == fold(written[0])
        ),
        None,
    )
    if project is None:
        return None
    pk, name = project
    rest = written[1:]
    if rest:
        pattern = read_path(join_levels(rest))
        if not any(levels.project[level] == pk for level in levels.matching(pattern)):
            return None
    pieces = [f"projet:{quoted(name)}"]
    if rest:
        pieces.append(f"{token.name}:{quoted(join_levels(rest))}")
    raw = " ".join(pieces)
    return Suggestion(rewrite(tokens, index, index + 1, raw), raw)


def close_paths(written: list[str], levels: Levels) -> list[str]:
    """Les chemins existants proches de celui écrit, tels qu'on les écrit : chaque
    niveau écrit est une partie du nom (au moins `CONTAINS_MIN_LENGTH` lettres) ou à
    peu de fautes de lui (même règle que le texte, #200). Les plus proches d'abord."""
    if written and written[-1].endswith(PREFIX_MARK):
        written = [*written[:-1], written[-1].rstrip(PREFIX_MARK).strip()]
    wanted = [reduce_text(level) for level in written if level]
    if not wanted:
        return []
    ranked = []
    for pk in levels.pks:
        chain = levels.chain(pk)
        if len(chain) < len(wanted):
            continue
        tail = chain[-len(wanted) :]
        score = 0
        for level, word in zip(tail, wanted, strict=True):
            distance = closeness(word, levels.reduced[level])
            if distance is None:
                break
            score += distance
        else:
            names = [levels.name[level] for level in tail]
            ranked.append((score, fold(join_levels(names)), join_levels(names)))
    return [written for _, _, written in sorted(ranked)]


def closeness(word: str, name: str) -> int | None:
    """0 si c'est le nom, 1 si `word` est une partie du nom, 2 + le nombre de fautes
    s'il est à peu de fautes ; `None` s'il n'est pas proche."""
    if word == name:
        return 0
    if len(word) >= CONTAINS_MIN_LENGTH and word in name:
        return 1
    distance = edit_distance(word, name)
    if distance <= tolerated_typos(word):
        return 2 + distance
    return None


def join_levels(names: list[str]) -> str:
    """Les niveaux tels qu'on les écrit : un « / » d'un nom se double (`split_path`)."""
    doubled = INPUT_SEPARATOR * 2
    return INPUT_SEPARATOR.join(
        name.replace(INPUT_SEPARATOR, doubled) for name in names
    )


def quoted(value: str) -> str:
    return f'"{value}"' if any(char.isspace() for char in value) else value


def operator_text(token: Token, value: str) -> str:
    """L'opérateur du jeton (nom tel que tapé, signe gardé) avec une autre valeur."""
    sign = "-" if token.negated else ""
    return f"{sign}{token.name}:{quoted(value)}"


def rewrite(tokens: list[Token], start: int, stop: int, raw: str) -> str:
    """La requête avec les jetons `start` à `stop` (exclu) remplacés par `raw`."""
    pieces = [t.raw for t in tokens[:start]] + [raw] + [t.raw for t in tokens[stop:]]
    return " ".join(pieces)
