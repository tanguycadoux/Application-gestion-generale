"""Incohérences entre une tâche, sa tâche parente et ses sous-tâches (#165).

Rien n'est empêché : les écarts sont seulement signalés, des deux côtés, avec
un lien vers l'autre tâche (`Task.incoherences`).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.dates import date_text

if TYPE_CHECKING:
    from .models import Task


@dataclass
class Incoherence:
    """Écart à corriger, et l'autre tâche concernée (#165)."""

    message: str
    task: Task


def pair_incoherences(
    parent: Task, child: Task, from_parent: bool
) -> list[Incoherence]:
    """Incohérences entre un parent et un de ses enfants, vues de l'un ou de l'autre."""
    found = []
    if parent.due_date and child.due_date and child.due_date > parent.due_date:
        parent_due = date_text(parent.due_date, "moyen")
        child_due = date_text(child.due_date, "moyen")
        found.append(
            Incoherence(
                f"L'échéance de la sous-tâche « {child} » ({child_due}) est après "
                f"celle-ci ({parent_due}).",
                child,
            )
            if from_parent
            else Incoherence(
                f"Son échéance ({child_due}) est après celle de la tâche parente "
                f"« {parent} » ({parent_due}).",
                parent,
            )
        )
    if child.project_id != parent.project_id:
        found.append(
            Incoherence(
                f"La sous-tâche « {child} » a un autre projet ({child.project}).",
                child,
            )
            if from_parent
            else Incoherence(
                f"Son projet ({child.project}) diffère de celui de la tâche parente "
                f"« {parent} » ({parent.project}).",
                parent,
            )
        )
    if parent.done and not child.done:
        found.append(
            Incoherence(
                f"Elle est terminée alors que la sous-tâche « {child} » ne l'est pas.",
                child,
            )
            if from_parent
            else Incoherence(
                f"Elle n'est pas terminée alors que la tâche parente « {parent} » "
                "l'est.",
                parent,
            )
        )
    return found
