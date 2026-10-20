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


@register.filter
def remaining_class(task) -> str:
    """Rouge en retard, ambre aujourd'hui et sous 3 jours, gris sinon."""
    days = _days_left(task)
    if days is not None and days < 0:
        return "text-red-800"
    if days is not None and days <= 3:
        return "text-amber-800"
    return "text-slate-600"


@register.filter
def indent_class(level: int) -> str:
    return INDENT_CLASSES[min(level, len(INDENT_CLASSES) - 1)]
