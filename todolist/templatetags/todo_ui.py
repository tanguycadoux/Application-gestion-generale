"""Affichage des tâches dans le tableau (#166), à charger avec `{% load todo_ui %}`.

Les classes Tailwind sont écrites en entier.
"""

from django import template
from django.utils import timezone

register = template.Library()

# Indentation du nom selon le niveau dans l'arbre, plafonnée au-delà.
INDENT_CLASSES = ["pl-0", "pl-6", "pl-12", "pl-18", "pl-24"]


def _days_left(task) -> int | None:
    if task.due_date is None or task.done:
        return None
    return (task.due_date - timezone.localdate()).days


def _duration(days: int) -> str:
    """Jusqu'à 30 jours en jours, jusqu'à 90 en semaines, au-delà en mois."""
    if days <= 30:
        return f"{days} j"
    if days <= 90:
        return f"{days // 7} sem."
    return f"{days // 30} mois"


@register.filter
def remaining_text(task) -> str:
    """« aujourd'hui », « dans 3 j », « 2 j de retard » ; rien sans échéance ou
    pour une tâche terminée."""
    days = _days_left(task)
    if days is None:
        return ""
    if days == 0:
        return "aujourd'hui"
    if days > 0:
        return f"dans {_duration(days)}"
    return f"{_duration(-days)} de retard"


# Seuil de l'échéance proche, en jours (ambre).
SOON_DAYS = 3


def due_signal(task) -> str:
    """Signal d'une tâche, commun au temps restant et à la barre d'avancement :
    `done` (succès), `overdue` (danger), `soon` (avertissement, sous 3 jours)
    ou `normal` (info, aussi sans échéance)."""
    if task.done:
        return "done"
    days = _days_left(task)
    if days is not None and days < 0:
        return "overdue"
    if days is not None and days <= SOON_DAYS:
        return "soon"
    return "normal"


REMAINING_CLASSES = {
    "overdue": "text-red-800",
    "soon": "text-amber-800",
}


@register.filter
def remaining_class(task) -> str:
    """Rouge en retard, ambre aujourd'hui et sous 3 jours, gris sinon."""
    return REMAINING_CLASSES.get(due_signal(task), "text-slate-600")


@register.filter
def indent_class(level: int) -> str:
    return INDENT_CLASSES[min(level, len(INDENT_CLASSES) - 1)]


PROGRESS_BAR = "block h-1.5 w-full appearance-none overflow-hidden rounded-full"
# Mêmes couleurs que les barres de progression des toasts (#154) : remplissage et
# fond clair de la même teinte, par signal (info, avertissement, erreur, succès).
PROGRESS_COLORS = {
    "normal": (
        " bg-blue-100 [&::-webkit-progress-bar]:bg-blue-100"
        " [&::-webkit-progress-value]:bg-blue-400 [&::-moz-progress-bar]:bg-blue-400"
    ),
    "soon": (
        " bg-amber-100 [&::-webkit-progress-bar]:bg-amber-100"
        " [&::-webkit-progress-value]:bg-amber-400 [&::-moz-progress-bar]:bg-amber-400"
    ),
    "overdue": (
        " bg-red-100 [&::-webkit-progress-bar]:bg-red-100"
        " [&::-webkit-progress-value]:bg-red-400 [&::-moz-progress-bar]:bg-red-400"
    ),
    "done": (
        " bg-green-200 [&::-webkit-progress-bar]:bg-green-200"
        " [&::-webkit-progress-value]:bg-green-500 [&::-moz-progress-bar]:bg-green-500"
    ),
}


@register.filter
def progress_classes(task) -> str:
    """Barre d'avancement (#182) aux couleurs du signal de son échéance."""
    return PROGRESS_BAR + PROGRESS_COLORS[due_signal(task)]
