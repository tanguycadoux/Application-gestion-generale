"""Tags que plus rien n'utilise (#296)."""

from .models import Tag


def forget_unused_tags() -> int:
    """Supprime les tags qu'aucune note part ni tâche n'utilise ; renvoie leur nombre.

    `core` ne connaît pas les apps : ce qui utilise un tag, ce sont les relations
    qui y mènent, lues sur le modèle.
    """
    unused = Tag.objects.all()
    for relation in Tag._meta.related_objects:
        unused = unused.filter(**{f"{relation.name}__isnull": True})
    pks = list(unused.values_list("pk", flat=True))
    Tag.objects.filter(pk__in=pks).delete()
    return len(pks)
