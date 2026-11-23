"""Titres de projet renommés dans une note, en attente du choix de l'utilisateur
(#170) : la suite proposée après l'enregistrement, et le ménage des renommages qui
ne tiennent plus.

Appelé par la vue qui enregistre la note (`add_pending_follow_up`), et non par
`services.process_passages` : la migration `0042_passages` recalcule les notes avec
le code d'aujourd'hui, avant que la table de ces renommages n'existe."""

from collections.abc import Iterable

from django.urls import reverse

from core.projects import clean_name, project_named

from .models import Note, Passage
from .signals import NoteFollowUp


def same_name(a: str, b: str) -> bool:
    """Deux noms de projet égaux, casse et espaces ignorés (#374)."""
    return clean_name(a).casefold() == clean_name(b).casefold()


def prune_pending_renames(note: Note, passages: Iterable[Passage]) -> None:
    """Oublie les renommages qui ne tiennent plus : le nouveau nom n'est plus un
    projet de la note (titre réécrit ou retiré à la main), ou l'ancien projet
    n'existe plus."""
    names = [passage.project.name for passage in passages if passage.project]
    for pending in note.pending_project_renames.all():
        written = any(same_name(pending.new_name, name) for name in names)
        if not written or project_named(pending.old_name) is None:
            pending.delete()


def pending_follow_up(note: Note) -> NoteFollowUp | None:
    """Le bilan des projets renommés dans cette note, s'il y en a en attente."""
    pending = list(note.pending_project_renames.all())
    if not pending:
        return None
    if len(pending) == 1:
        label = f"Projet « {pending[0].old_name} » renommé « {pending[0].new_name} »"
    else:
        label = f"{len(pending)} projets renommés"
    return NoteFollowUp(
        label, reverse("note_taking:project_rename_review", args=[str(note.date)])
    )


def add_pending_follow_up(note: Note) -> None:
    """Après le recalcul d'une note enregistrée : oublie les renommages qui ne
    tiennent plus, et met le bilan des projets renommés en tête des suites (il
    peut changer les projets des tâches, que le bilan des tâches montre ensuite)."""
    prune_pending_renames(note, note.passages.select_related("project"))
    renamed = pending_follow_up(note)
    if renamed is not None:
        note.follow_ups = (renamed, *note.follow_ups)
