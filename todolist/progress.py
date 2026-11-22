"""Propagation de l'avancement d'une tâche à ses ancêtres (#164).

`Task.save` l'appelle après chaque enregistrement ; la suppression d'une tâche
l'appelle aussi, par le signal `post_delete` branché ici (module chargé par
`TodolistConfig.ready`).
"""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Task


def update_ancestors_progress(parent_id: int | None) -> list[int]:
    """Recalcule l'avancement des ancêtres, du parent jusqu'à la racine (#164).

    Un parent coché se décoche dès qu'un de ses enfants n'est plus terminé ; un
    parent sans plus d'enfant garde ses dernières valeurs. Renvoie les
    identifiants des tâches modifiées.
    """
    updated = []
    while parent_id is not None:
        parent = Task.objects.filter(pk=parent_id).first()
        if parent is None:
            break
        computed = parent.children_progress()
        if computed is None:
            break
        done = parent.done and not parent.children.filter(done=False).exists()
        if (computed, done) == (parent.progress, parent.done):
            break
        Task.objects.filter(pk=parent.pk).update(
            progress=computed,
            done=done,
            completed_at=parent.completed_at if done else None,
        )
        updated.append(parent.pk)
        parent_id = parent.parent_id
    return updated


@receiver(post_delete, sender=Task)
def update_progress_after_delete(sender, instance: Task, **kwargs):
    update_ancestors_progress(instance.parent_id)
