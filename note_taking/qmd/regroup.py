"""Regrouper les titres répétés d'une note (#315).

Une note où un titre revient sous un même parent (`# A`, `# B`, `# A`, ou `## x`
deux fois sous `# A`) peut être réorganisée pour que chaque titre n'y soit écrit
qu'une fois. Rien n'est fait à l'enregistrement : la note est gardée telle
qu'écrite, et le regroupement est **proposé**, titre par titre, avec un aperçu.

Règle : les occurrences suivantes rejoignent la première. Le texte qui suit
directement leur titre, avant tout sous-titre, se place après celui de la première
et avant ses sous-titres ; leurs sous-titres de même nom fusionnent à leur tour, à
tous les niveaux, les autres s'ajoutent à la suite de ceux de la première.

Deux titres sont le même s'ils ont le même niveau et le même texte, tel qu'écrit
(attributs et casse compris) : c'est ce qui fait le chemin des tâches issues des
notes (#240). Le chemin de chaque ligne ne change donc pas au regroupement.

Un regroupement n'est pas proposé s'il changerait ce que l'analyse tire du texte :
- un bloc `{.metadata}` (tags, `todo`) vaudrait pour un autre texte qu'avant ;
- le texte déplacé commence en retrait, et continuerait une liste du texte qui le
  précède alors : une tâche pourrait changer de parent, donc d'identité.

Les titres suivent l'analyse du parseur : ceux d'un bloc de code ou d'un callout ne
comptent pas.
"""

from collections import Counter
from dataclasses import dataclass, field

from ..exceptions import NoteParseError, RegroupError
from .parser import HEADING_SEPARATOR, ParsedNote, parse_note

# Raisons pour lesquelles un regroupement n'est pas proposé.
BLOCKED_METADATA = (
    "un bloc {.metadata} (tags, todo) ne vaudrait plus pour le même texte : à "
    "regrouper à la main."
)
BLOCKED_LIST = (
    "le texte déplacé commence en retrait et continuerait une liste : une tâche "
    "pourrait changer de parent. À regrouper à la main."
)


@dataclass
class Node:
    """Un titre et le texte qui le suit avant le titre suivant ; ou, au niveau 0,
    le début de la note avant le premier titre."""

    rank: int  # rang dans la note, pour savoir ce qui se suivait
    level: int
    title: str | None
    line: int  # ligne du titre, à partir de 1 ; 0 pour le début de la note
    lines: list[str]  # le titre, puis son texte
    children: list[Node] = field(default_factory=list)
    # Texte des occurrences regroupées dans celle-ci, dans l'ordre.
    moved: list[list[str]] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, str | None]:
        return self.level, self.title


@dataclass
class Occurrence:
    line: int
    # Nombre de lignes du titre et de tout ce qui est sous lui.
    size: int

    @property
    def last_line(self) -> int:
        return self.line + self.size - 1


@dataclass
class RepeatedHeading:
    """Un titre écrit plusieurs fois sous le même parent."""

    # Identifie le regroupement dans le formulaire : la ligne de la première
    # occurrence, qui reçoit les autres.
    key: str
    level: int
    title: str
    # Les titres au-dessus, du projet au parent.
    parents: list[str]
    occurrences: list[Occurrence]
    # Sous-titres qui fusionnent aussi, entraînés par celui-ci.
    nested: list[str] = field(default_factory=list)
    # Raison pour laquelle il n'est pas proposé ; vide s'il l'est.
    blocked: str = ""

    @property
    def written(self) -> str:
        """Le titre tel qu'écrit : « ## x »."""
        return f"{'#' * self.level} {self.title}"

    @property
    def chain(self) -> str:
        """Les titres au-dessus, puis lui : « A › x »."""
        return HEADING_SEPARATOR.join([*self.parents, self.title])

    @property
    def first(self) -> Occurrence:
        return self.occurrences[0]

    @property
    def others(self) -> list[Occurrence]:
        return self.occurrences[1:]


def is_blank(line: str) -> bool:
    return not line.strip()


def without_blank_edges(lines: list[str]) -> list[str]:
    start = 0
    while start < len(lines) and is_blank(lines[start]):
        start += 1
    end = len(lines)
    while end > start and is_blank(lines[end - 1]):
        end -= 1
    return lines[start:end]


def trailing_blanks(lines: list[str]) -> list[str]:
    end = len(lines)
    while end > 0 and is_blank(lines[end - 1]):
        end -= 1
    return lines[end:]


class Document:
    """L'arbre des titres d'un texte de note, et sa réécriture."""

    def __init__(self, body: str, parsed: ParsedNote):
        lines = body.split("\n")
        # Les lignes vides de la fin restent à la fin, quoi qu'on déplace.
        self.tail = trailing_blanks(lines)
        lines = lines[: len(lines) - len(self.tail)]
        self.blank = "\r" if "\r\n" in body else ""
        self.problems: list[str] = []

        starts = [line for line, _ in parsed.heading_lines]
        first = starts[0] - 1 if starts else len(lines)
        self.root = Node(0, 0, None, 0, lines[:first])
        stack = [self.root]
        for rank, ((line, level), title) in enumerate(
            zip(parsed.heading_lines, parsed.headings, strict=True), start=1
        ):
            end = starts[rank] - 1 if rank < len(starts) else len(lines)
            node = Node(rank, level, title, line, lines[line - 1 : end])
            while stack[-1].level >= level:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)

    # Repérage

    def repeated(self) -> list[RepeatedHeading]:
        found: list[RepeatedHeading] = []
        self.collect(self.root, [], found)
        return found

    def collect(self, node: Node, parents: list[str], found: list[RepeatedHeading]):
        groups: dict[tuple[int, str | None], list[Node]] = {}
        for child in node.children:
            groups.setdefault(child.key, []).append(child)
        for child in node.children:
            group = groups.get(child.key, [])
            if len(group) > 1 and group[0] is child:
                found.append(
                    RepeatedHeading(
                        key=str(child.line),
                        level=child.level,
                        title=child.title or "",
                        parents=parents,
                        occurrences=[
                            Occurrence(other.line, subtree_size(other))
                            for other in group
                        ],
                    )
                )
            self.collect(child, [*parents, child.title or ""], found)

    # Regroupement

    def regroup(self, keys: set[str]) -> list[str]:
        """Regroupe les titres choisis ; renvoie les sous-titres qui ont fusionné
        avec eux."""
        nested: list[str] = []
        self.regroup_children(self.root, keys, nested)
        return nested

    def regroup_children(self, node: Node, keys: set[str], nested: list[str]):
        kept: list[Node] = []
        firsts: dict[tuple[int, str | None], Node] = {}
        for child in node.children:
            first = firsts.get(child.key)
            if first is not None and str(first.line) in keys:
                self.merge(first, child, nested)
            else:
                firsts.setdefault(child.key, child)
                kept.append(child)
        node.children = kept
        for child in kept:
            self.regroup_children(child, keys, nested)

    def merge(self, target: Node, other: Node, nested: list[str], depth: int = 0):
        """Ajoute `other` à `target` : son texte après celui de `target`, ses
        sous-titres de même nom fusionnés, les autres à la suite."""
        if depth:
            nested.append(target.title or "")
        text = without_blank_edges(other.lines[1:])
        if text:
            has_text = without_blank_edges(target.lines[1:]) or target.moved
            if has_text and text[0][:1].isspace():
                self.problems.append(BLOCKED_LIST)
            target.moved.append(text)
        target.moved.extend(other.moved)
        for child in other.children:
            same = next(
                (mine for mine in target.children if mine.key == child.key), None
            )
            if same is None:
                target.children.append(child)
            else:
                self.merge(same, child, nested, depth + 1)

    # Écriture

    def text(self) -> str:
        blocks: list[tuple[Node, list[str]]] = []
        self.emit(self.root, blocks)
        lines: list[str] = []
        previous: Node | None = None
        for node, block in blocks:
            # Deux morceaux qui ne se suivaient pas, ou un morceau qui finit par du
            # texte déplacé : une ligne vide entre eux, pour qu'un titre ne se colle
            # pas au texte d'avant.
            if (
                previous is not None
                and (node.rank != previous.rank + 1 or previous.moved)
                and lines
                and not is_blank(lines[-1])
            ):
                lines.append(self.blank)
            lines.extend(block)
            previous = node
        while lines and is_blank(lines[-1]):
            lines.pop()
        return "\n".join([*lines, *self.tail])

    def emit(self, node: Node, blocks: list[tuple[Node, list[str]]]):
        if node.moved:
            own = node.lines
            end = len(own) - len(trailing_blanks(own))
            block = own[:end]
            for text in node.moved:
                # Sous un titre sans texte, le texte déplacé le suit directement.
                gap = [self.blank] if len(block) > 1 else []
                block = [*block, *gap, *text]
            block.extend(own[end:])
        else:
            block = node.lines
        if block:
            blocks.append((node, block))
        for child in node.children:
            self.emit(child, blocks)


def subtree_size(node: Node) -> int:
    return len(node.lines) + sum(subtree_size(child) for child in node.children)


def analysed_lines(parsed: ParsedNote) -> Counter:
    """Chaque ligne de texte avec ses titres et ses tags : ce que l'analyse en
    tire, et que le regroupement doit garder."""
    return Counter(
        (tuple(passage.headings), tuple(passage.tags), line.strip())
        for passage in parsed.passages
        for line in passage.lines
        if line.strip()
    )


def document(body: str) -> Document | None:
    try:
        return Document(body, parse_note("", body))
    except NoteParseError:
        return None


def repeated_headings(body: str) -> list[RepeatedHeading]:
    """Les titres répétés d'un texte de note, chacun avec son aperçu et, s'il
    n'est pas proposé, la raison. Aucun si le texte ne s'analyse pas."""
    doc = document(body)
    if doc is None:
        return []
    before = analysed_lines(parse_note("", body))
    found = doc.repeated()
    for heading in found:
        trial = document(body)
        assert trial is not None
        heading.nested = sorted(set(trial.regroup({heading.key})))
        if trial.problems:
            heading.blocked = trial.problems[0]
            continue
        try:
            after = analysed_lines(parse_note("", trial.text()))
        except NoteParseError:
            after = Counter()
        if after != before:
            heading.blocked = BLOCKED_METADATA
    return found


def regroup_headings(body: str, keys: set[str]) -> str:
    """Le texte de la note, les titres choisis regroupés (`RepeatedHeading.key`).

    Refusé (`RegroupError`) si un titre choisi n'est plus répété ou n'est pas
    proposé (la note a changé depuis l'aperçu), ou si les titres choisis, ensemble,
    changeraient ce que l'analyse tire du texte."""
    allowed = {
        heading.key for heading in repeated_headings(body) if not heading.blocked
    }
    if not keys or keys - allowed:
        raise RegroupError(
            "La note a changé depuis l'aperçu : un titre choisi n'est plus à "
            "regrouper. Rien n'a été modifié ; revoir l'aperçu."
        )
    doc = document(body)
    assert doc is not None
    doc.regroup(keys)
    text = doc.text()
    if doc.problems or analysed_lines(parse_note("", text)) != analysed_lines(
        parse_note("", body)
    ):
        raise RegroupError(
            "Ces titres, regroupés ensemble, changeraient les tags ou les listes de "
            "la note. Rien n'a été modifié ; les regrouper un à un."
        )
    return text
