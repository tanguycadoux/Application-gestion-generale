"""Requête de recherche (#199) : une zone de texte, à la Google. **Sans accès à la base.**

    projet:Alpha tag:urgent chemin:Réunion/Préparation date:2026-09..2026-10
    "résistance thermique" therm* -brouillon -tag:fini

- `projet:`, `tag:`, `chemin:` (niveaux séparés par « / », à toute profondeur, descendants compris) ;
  guillemets pour une valeur à espaces : `projet:"Mon projet"`. Les noms
  d'opérateurs ignorent casse et accents. Un mot suivi de deux-points qui n'est pas
  un opérateur reste du texte (« Re:thinking »).
- `date:` année, mois ou jour, ou une plage `a..b` (une borne peut manquer), bornes
  incluses : `date:2026-10` couvre tout octobre.
- `"phrase exacte"`, `mot*` (préfixe), `-mot` ou `-"phrase"` (exclusion), `-tag:x`.
- Une requête mal écrite ne lève jamais : la partie illisible est cherchée telle
  quelle, et signalée dans `errors`.
"""

import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

# Nom d'opérateur, sans accents ni casse, vers le champ de la requête qu'il remplit.
OPERATORS = {
    "projet": "projects",
    "tag": "tags",
    "chemin": "paths",
    "date": "date",
}
NAME_REGEX = re.compile(r"(?P<name>[^\W\d_]+):")
DATE_PART_REGEX = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
DATE_RANGE_REGEX = re.compile(r"^(?P<start>[\d-]*)(?P<dots>\.\.)?(?P<end>[\d-]*)$")
DATE_HELP = "écrire 2026, 2026-10, 2026-09-15, 2026-09..2026-10, 2026-09.. ou ..2026."


@dataclass(frozen=True)
class Term:
    """Un morceau de texte libre : `kind` vaut `word`, `prefix` ou `phrase`."""

    text: str
    kind: str = "word"
    negated: bool = False


@dataclass
class SearchQuery:
    terms: list[Term] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    not_projects: list[str] = field(default_factory=list)
    not_tags: list[str] = field(default_factory=list)
    not_paths: list[str] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    errors: list[str] = field(default_factory=list)
    # Mots élargis par la recherche (#200) : (écrit, trouvé), rempli par `search_note_parts`.
    expansions: list[tuple[str, str]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(
            self.terms
            or self.projects
            or self.tags
            or self.paths
            or self.not_projects
            or self.not_tags
            or self.not_paths
            or self.date_from
            or self.date_to
        )


@dataclass
class Token:
    raw: str
    negated: bool
    name: str | None  # avant les deux-points, tel que saisi
    value: str
    quoted: bool
    unclosed: bool


def fold_name(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def read_tokens(text: str) -> list[Token]:
    """Découpe en jetons : `-`, `nom:`, puis une valeur nue ou entre guillemets."""
    tokens = []
    index, size = 0, len(text)
    while index < size:
        if text[index].isspace():
            index += 1
            continue
        start = index
        negated = (
            text[index] == "-" and index + 1 < size and not text[index + 1].isspace()
        )
        if negated:
            index += 1
        name = None
        match = NAME_REGEX.match(text, index)
        if match:
            name = match.group("name")
            index = match.end()
        quoted = unclosed = False
        if index < size and text[index] == '"':
            quoted = True
            end = text.find('"', index + 1)
            if end == -1:
                unclosed = True
                value, index = text[index + 1 :], size
            else:
                value, index = text[index + 1 : end], end + 1
        else:
            end = index
            while end < size and not text[end].isspace():
                end += 1
            value, index = text[index:end], end
        tokens.append(Token(text[start:index], negated, name, value, quoted, unclosed))
    return tokens


def parse_query(text: str | None) -> SearchQuery:
    query = SearchQuery()
    for token in read_tokens(text or ""):
        if token.unclosed:
            query.errors.append(
                f"Guillemet non fermé : « {token.raw} » est lu jusqu'à la fin."
            )
        target = OPERATORS.get(fold_name(token.name)) if token.name else None
        if token.name and target is None:
            # Pas un opérateur : du texte, deux-points compris (« Re:thinking »).
            add_term(query, Term(f"{token.name}:{token.value}", "word", token.negated))
        elif target is None:
            add_plain(query, token)
        elif not token.value.strip():
            continue
        elif target == "date":
            add_date(query, token)
        else:
            attribute = ("not_" if token.negated else "") + target
            getattr(query, attribute).append(token.value.strip())
    return query


def add_term(query: SearchQuery, term: Term) -> None:
    """Un terme sans lettre ni chiffre (« , », « - ») ne dit rien à chercher."""
    if any(char.isalnum() for char in term.text):
        query.terms.append(term)


def add_plain(query: SearchQuery, token: Token) -> None:
    value = token.value.strip()
    if token.quoted:
        add_term(query, Term(value, "phrase", token.negated))
    elif value.endswith("*"):
        add_term(query, Term(value.rstrip("*"), "prefix", token.negated))
    else:
        add_term(query, Term(value, "word", token.negated))


def add_date(query: SearchQuery, token: Token) -> None:
    try:
        if token.negated:
            raise ValueError
        start, end = read_dates(token.value.strip())
    except ValueError:
        query.errors.append(f"date:{token.value} : {DATE_HELP}")
        add_term(query, Term(f"date:{token.value}"))
        return
    if start and (query.date_from is None or start > query.date_from):
        query.date_from = start
    if end and (query.date_to is None or end < query.date_to):
        query.date_to = end


def read_dates(value: str) -> tuple[date | None, date | None]:
    """`2026-10`, `2026-09..2026-10`, `2026-09-15..` ou `..2026`, bornes incluses."""
    match = DATE_RANGE_REGEX.match(value)
    if not match or not (match["start"] or match["end"]):
        raise ValueError(value)
    if match["start"] and match["end"] and not match["dots"]:
        raise ValueError(value)
    start = period(match["start"])[0] if match["start"] else None
    end = period(match["end"])[1] if match["end"] else None
    if not match["dots"]:
        end = period(match["start"])[1]
    if start and end and start > end:
        # Bornes inversées : `2026-10..2026-09` est la même plage.
        start, end = period(match["end"])[0], period(match["start"])[1]
    return start, end


def period(text: str) -> tuple[date, date]:
    """Premier et dernier jour de l'année, du mois ou du jour écrit."""
    match = DATE_PART_REGEX.match(text)
    if not match:
        raise ValueError(text)
    year, month, day = (int(part) if part else None for part in match.groups())
    assert year is not None
    if day and month:
        single = date(year, month, day)
        return single, single
    if month:
        return date(year, month, 1), date(
            year, month, calendar.monthrange(year, month)[1]
        )
    return date(year, 1, 1), date(year, 12, 31)
