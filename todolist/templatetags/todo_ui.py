"""Classes Tailwind des TODO selon leur échéance, à charger avec `{% load todo_ui %}`.

Chaque filtre reçoit `todo.due_status` (`None`, `normal`, `soon`, `today` ou
`overdue`) et renvoie les classes de l'élément, écrites en entier.
"""

from django import template

register = template.Library()

CARD = (
    "relative col-span-full grid grid-cols-subgrid items-baseline"
    " rounded-[.6rem] p-[.4rem]"
)
# Contour intérieur des TODO du jour et en retard.
CARD_OUTLINE = (
    " after:pointer-events-none after:absolute after:inset-0"
    " after:rounded-[.6rem] after:border-[.2rem]"
)
CARD_CLASSES = {
    "soon": CARD + " bg-primary-95",
    "today": CARD + " bg-primary-95" + CARD_OUTLINE + " after:border-primary-60",
    "overdue": CARD + " bg-alert-90" + CARD_OUTLINE + " after:border-alert-60",
}
CARD_DEFAULT = CARD + " bg-neutral-95"

LINE = "grid grid-cols-[1fr_auto] items-baseline"
LINE_CLASSES = {
    "soon": LINE + " font-semibold text-primary-40",
    "today": LINE + " font-semibold text-primary-40",
    "overdue": LINE + " font-semibold text-alert-40",
}

CHILD = "p-[.4rem] not-first:border-t not-first:border-neutral-50"
CHILD_CLASSES = {
    "soon": CHILD + " bg-primary-95",
    "today": CHILD + " bg-primary-95",
    "overdue": CHILD + " bg-alert-90",
}
CHILD_DEFAULT = CHILD + " bg-neutral-95"


@register.filter
def todo_card_classes(status: str | None) -> str:
    """Carte d'une TODO de premier niveau dans la liste."""
    return CARD_CLASSES.get(status or "", CARD_DEFAULT)


@register.filter
def todo_line_classes(status: str | None) -> str:
    """Ligne titre + échéance, en gras et en couleur si l'échéance est proche."""
    return LINE_CLASSES.get(status or "", LINE)


@register.filter
def todo_child_classes(status: str | None) -> str:
    """Sous-tâche, dans la liste encadrée des sous-tâches."""
    return CHILD_CLASSES.get(status or "", CHILD_DEFAULT)
