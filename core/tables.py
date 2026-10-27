"""Tableaux triables et filtrables côté serveur, dans l'URL (#178).

Modèle : `research-paper-relationship-graph`. Le tri (`?sort=date`, `?sort=-date`) et
les filtres (`?project=…&date_from=2025-11-01`) sont des paramètres d'URL : la page
se partage, fonctionne sans JavaScript, et tout le tableau est trié et filtré, pas
seulement ce qui est affiché. Ce module ne connaît aucune app : chaque tableau
déclare ses colonnes (`Sorting`) et ses filtres (`Filters`), et les composants
`{% column_header %}` et `{% filter_summary %}` (`core/templatetags/ui.py`) les
affichent.

Le tri et les filtres s'appliquent à une liste d'objets de la page elle-même :
`Sorting.apply` à un queryset (expression SQL), `sort_items` à une liste Python
(tableau arborescent), et chaque filtre porte la fonction qui sait le filtrer.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.http import HttpRequest


@dataclass(frozen=True)
class Sort:
    column: str
    descending: bool = False

    @property
    def param(self) -> str:
        return f"-{self.column}" if self.descending else self.column


@dataclass(frozen=True)
class Column:
    """Une colonne triable : une expression (queryset) ou une clé (liste Python)."""

    expression: Any = None
    key: Callable[[Any], Any] | None = None
    # Sens du premier clic : les dates récentes d'abord, les noms de A à Z.
    descending_first: bool = False


class Sorting:
    """Les colonnes triables d'un tableau ; les égalités sont toujours départagées
    dans le même ordre, jusqu'à l'identifiant, pour qu'une ligne ne change pas de
    place d'un affichage à l'autre."""

    def __init__(
        self, columns: Mapping[str, Column], default: Sort, ties: Sequence[Any] = ()
    ):
        self.columns = dict(columns)
        self.default = default
        self.ties = tuple(ties)

    def read(self, value: str | None) -> Sort:
        """Le tri demandé par `?sort=`, le tri par défaut s'il ne nomme aucune colonne."""
        value = value or ""
        column = value.removeprefix("-")
        if column not in self.columns:
            return self.default
        return Sort(column, value.startswith("-"))

    def next_sort(self, current: Sort, column: str) -> Sort:
        """Le tri d'un clic sur l'en-tête : l'autre sens si la colonne est déjà triée."""
        if current.column == column:
            return Sort(column, not current.descending)
        return Sort(column, self.columns[column].descending_first)

    def apply(self, queryset, sort: Sort):
        """Trie un queryset ; les lignes sans valeur restent à la fin dans les deux sens."""
        expression = self.columns[sort.column].expression
        first = (
            expression.desc(nulls_last=True)
            if sort.descending
            else expression.asc(nulls_last=True)
        )
        return queryset.order_by(first, *(tie.asc() for tie in self.ties), "pk")

    def sort_items(self, items: Iterable[Any], sort: Sort, tie: Callable | None = None):
        """Trie une liste Python par la clé de la colonne. Les valeurs absentes
        (`None`) restent à la fin dans les deux sens ; `tie` départage les égalités."""
        key = self.columns[sort.column].key
        assert key is not None, f"La colonne {sort.column} n'a pas de clé de tri."
        items = list(items)
        if tie is not None:
            items.sort(key=tie)
        present = [item for item in items if key(item) is not None]
        missing = [item for item in items if key(item) is None]
        # Le tri de Python est stable, même à rebours : les égalités gardent l'ordre de `tie`.
        present.sort(key=key, reverse=sort.descending)
        return present + missing


class Filter:
    """Un filtre : ses paramètres d'URL, sa lecture, sa description, son application.

    `key` nomme le filtre dans `ActiveFilters`, `apply(cible, valeur)` le met en
    œuvre sur ce que la page filtre (un queryset, souvent).
    """

    kind = ""

    def __init__(
        self,
        key: str,
        label: str,
        apply: Callable[[Any, Any], Any],
        params: Sequence[str] | None = None,
    ):
        self.key = key
        self.label = label
        self.params = tuple(params or (key,))
        self._apply = apply

    def read(self, data: Mapping[str, str], errors: list[str]) -> Any:
        """La valeur demandée, ou None si le filtre n'est pas actif."""
        raise NotImplementedError

    def describe(self, value: Any) -> str:
        raise NotImplementedError

    def apply(self, target: Any, value: Any) -> Any:
        return self._apply(target, value)


class TextFilter(Filter):
    """La colonne contient un texte."""

    kind = "text"

    def read(self, data, errors):
        return data.get(self.params[0], "").strip() or None

    def describe(self, value):
        return f"contient « {value} »"


@dataclass(frozen=True)
class Choice:
    value: str
    label: str
    # Un projet : le choix s'affiche avec sa pastille de couleur (#162).
    project: Any = None


class ChoiceFilter(Filter):
    """Un choix parmi quelques-uns, donnés ou calculés à l'affichage.

    Avec `default`, c'est la valeur du tableau sans paramètre : elle ne compte pas
    comme un filtre actif, mais elle est cochée dans la liste.
    """

    kind = "choice"

    def __init__(
        self,
        key: str,
        label: str,
        choices: Sequence[Choice | tuple[str, str]]
        | Callable[[], Sequence[Choice | tuple[str, str]]],
        apply: Callable[[Any, Any], Any],
        default: str | None = None,
    ):
        super().__init__(key, label, apply)
        self._choices = choices
        self.default = default

    def choices(self) -> list[Choice]:
        raw = self._choices() if callable(self._choices) else self._choices
        return [c if isinstance(c, Choice) else Choice(*c) for c in raw]

    def read(self, data, errors):
        value = data.get(self.params[0], "")
        if value == self.default or value not in {c.value for c in self.choices()}:
            return None
        return value

    def describe(self, value):
        return next(c.label for c in self.choices() if c.value == value)


class DateRangeFilter(Filter):
    """Des dates `AAAA-MM-JJ` : depuis, jusqu'à, ou entre les deux."""

    kind = "dates"

    def __init__(self, key: str, label: str, apply: Callable[[Any, Any], Any]):
        super().__init__(key, label, apply, (f"{key}_from", f"{key}_to"))

    def read(self, data, errors):
        dates: list[date | None] = []
        for param in self.params:
            raw = data.get(param, "").strip()
            parsed = None
            if raw:
                try:
                    parsed = date.fromisoformat(raw)
                except ValueError:
                    errors.append(
                        f"{self.label} : « {raw} » n'est pas une date (AAAA-MM-JJ)."
                    )
            dates.append(parsed)
        start, end = dates
        if start and end and start > end:
            start, end = end, start
        return (start, end) if start or end else None

    def describe(self, value):
        start, end = value
        if start and end:
            return str(start) if start == end else f"du {start} au {end}"
        return f"depuis le {start}" if start else f"jusqu'au {end}"


@dataclass
class ActiveFilters:
    """Les filtres demandés par l'URL : valeur de chaque filtre actif, erreurs de saisie."""

    values: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.values)


class Filters:
    """Les filtres d'un tableau, rangés par colonne : une colonne peut en porter
    plusieurs, réunis dans le même panneau."""

    def __init__(self, columns: Mapping[str, Sequence[Filter]]):
        self.columns = {column: tuple(filters) for column, filters in columns.items()}

    @property
    def all(self) -> list[Filter]:
        return [f for filters in self.columns.values() for f in filters]

    def read(self, data: Mapping[str, str]) -> ActiveFilters:
        active = ActiveFilters()
        for column_filter in self.all:
            value = column_filter.read(data, active.errors)
            if value is not None:
                active.values[column_filter.key] = value
        return active

    def apply(self, target: Any, active: ActiveFilters) -> Any:
        for column_filter in self.all:
            if column_filter.key in active.values:
                target = column_filter.apply(target, active.values[column_filter.key])
        return target


# --- Ce qu'affichent les composants {% column_header %} et {% filter_summary %} ---

# Sauf pour la page : elle repart de la première à chaque changement de tri ou de filtre.
PAGE_PARAM = "page"
MAX_RADIO_CHOICES = 6


def url_without(request: HttpRequest, params: Iterable[str]) -> str:
    """L'URL courante sans ces paramètres (et sans la page)."""
    query = request.GET.copy()
    for param in (*params, PAGE_PARAM):
        query.pop(param, None)
    return f"?{query.urlencode()}" if query else request.path


def filter_panel(
    request: HttpRequest,
    filters: Filters | None,
    active: ActiveFilters | None,
    column: str,
) -> dict[str, Any] | None:
    """Le panneau de filtres d'une colonne, ou None si elle n'en a pas."""
    if not filters or column not in filters.columns:
        return None
    column_filters = filters.columns[column]
    params = [param for f in column_filters for param in f.params]
    values = active.values if active else {}
    # Le formulaire de la colonne garde le tri et les autres filtres en champs cachés.
    kept = [
        (name, item)
        for name, items in request.GET.lists()
        if name not in (*params, PAGE_PARAM)
        for item in items
    ]
    fields = []
    for column_filter in column_filters:
        field_data: dict[str, Any] = {
            "kind": column_filter.kind,
            "label": column_filter.label,
            "id": f"filter-{column_filter.key}",
            "params": column_filter.params,
            "values": [request.GET.get(param, "") for param in column_filter.params],
        }
        if isinstance(column_filter, ChoiceFilter):
            raw = request.GET.get(column_filter.params[0], "")
            field_data["choices"] = column_filter.choices()
            # Une longue liste de choix est un <select>, une courte des boutons radio ;
            # des projets restent des boutons radio, un <select> n'a pas de pastille.
            field_data["many"] = len(
                field_data["choices"]
            ) > MAX_RADIO_CHOICES and not any(c.project for c in field_data["choices"])
            field_data["selected"] = raw or column_filter.default or ""
            field_data["has_default"] = column_filter.default is not None
        fields.append(field_data)
    return {
        "id": f"filters-{column}",
        "label": " et ".join(f.label.lower() for f in column_filters),
        "fields": fields,
        "kept": kept,
        "active": any(f.key in values for f in column_filters),
        "remove_url": url_without(request, params),
    }


def header_context(
    request: HttpRequest,
    label: str,
    column: str,
    sorting: Sorting | None,
    sort: Sort | None,
    filters: Filters | None,
    active: ActiveFilters | None,
) -> dict[str, Any]:
    """Le contexte de `{% column_header %}` : lien de tri, flèche, entonnoir."""
    header: dict[str, Any] = {
        "label": label,
        "url": "",
        "filter": filter_panel(request, filters, active, column),
    }
    if not sorting or sort is None or column not in sorting.columns:
        return header
    query = request.GET.copy()
    query.pop(PAGE_PARAM, None)
    query["sort"] = sorting.next_sort(sort, column).param
    here = sort.column == column
    header.update(
        {
            "url": f"?{query.urlencode()}",
            "aria_sort": ("descending" if sort.descending else "ascending")
            if here
            else "",
            "arrow": ("arrow_downward" if sort.descending else "arrow_upward")
            if here
            else "",
        }
    )
    return header


def summary_context(
    request: HttpRequest, filters: Filters | None, active: ActiveFilters | None
) -> dict[str, Any]:
    """Le contexte de `{% filter_summary %}` : chaque filtre actif, retirable d'un clic."""
    if not filters or active is None:
        return {"active": [], "errors": []}
    items = [
        {
            "text": f"{f.label} : {f.describe(active.values[f.key])}",
            "remove_url": url_without(request, f.params),
        }
        for f in filters.all
        if f.key in active.values
    ]
    return {
        "active": items,
        "errors": active.errors,
        "clear_url": url_without(
            request, [param for f in filters.all for param in f.params]
        ),
    }
