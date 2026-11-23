"""Un nom de projet ignore la casse, comme un niveau (#374).

Les projets dont les noms ne diffèrent que par la casse (et les espaces) sont
réunis en un seul. **Projet gardé** : le plus utilisé (passages et tâches, écartées
comprises, comptés ensemble), à égalité le plus ancien (plus petite clé) ; il garde
son nom, sa casse et sa couleur, et reprend la description d'un projet réuni si la
sienne est vide.

Ce qui utilisait un projet réuni passe au projet gardé : passages, tâches,
recherches enregistrées. Ses niveaux aussi : un premier niveau de même nom (casse
ignorée) qu'un premier niveau du projet gardé le rejoint, avec ses sous-niveaux
(réunis à leur tour s'ils ont le même nom) ; les autres passent sous le projet gardé
avec tous leurs descendants.

Rien n'est à recalculer : les titres des notes ne changent pas (l'identité des
tâches, #240, se fait sur le titre tel qu'écrit), et le prochain enregistrement
d'une note retrouve le projet gardé, casse ignorée.

`core` ne connaît pas les apps : ce qui utilise un projet ou un niveau est lu sur
le modèle, comme `forget_unused_sections`. Pas de retour en arrière.
"""

from django.db import migrations


def repoint(model, gone, keep, skip=()) -> None:
    """Ce qui mène à `gone` mène désormais à `keep` (sauf les modèles `skip`)."""
    for relation in model._meta.related_objects:
        if relation.related_model is model or relation.related_model in skip:
            continue
        name = relation.field.name
        related = relation.related_model._base_manager
        if relation.one_to_many:
            related.filter(**{name: gone}).update(**{name: keep})
        elif relation.many_to_many:
            for obj in related.filter(**{name: gone}):
                getattr(obj, name).remove(gone)
                getattr(obj, name).add(keep)


def usage(Project, Section, project) -> int:
    """Passages et tâches (tout ce qui mène au projet, hors niveaux)."""
    return sum(
        relation.related_model._base_manager.filter(
            **{relation.field.name: project}
        ).count()
        for relation in Project._meta.related_objects
        if relation.one_to_many and relation.related_model is not Section
    )


def child_named(Section, project_id, parent, name):
    for sibling in Section.objects.filter(project_id=project_id, parent=parent):
        if sibling.name.casefold() == name.casefold():
            return sibling
    return None


def move_subtree(Section, root, project, parent) -> None:
    """`root` passe sous `parent` (None : premier niveau), dans `project`, avec ses
    descendants."""
    root.parent = parent
    root.project = project
    root.save(update_fields=["parent", "project"])
    pending = list(Section.objects.filter(parent=root))
    while pending:
        section = pending.pop()
        section.project = project
        section.save(update_fields=["project"])
        pending.extend(Section.objects.filter(parent=section))


def merge_section(Section, gone, keep) -> None:
    """`gone` rejoint `keep` (voir 0008), même d'un autre projet : ses sous-niveaux
    de même nom sont réunis à leur tour, les autres passent sous `keep`."""
    for child in list(Section.objects.filter(parent=gone)):
        twin = child_named(Section, keep.project_id, keep, child.name)
        if twin is None:
            move_subtree(Section, child, keep.project, keep)
        else:
            merge_section(Section, child, twin)
    repoint(Section, gone, keep)
    gone.delete()


def merge_project(Project, Section, gone, keep) -> None:
    for root in list(Section.objects.filter(project=gone, parent=None)):
        twin = child_named(Section, keep.pk, None, root.name)
        if twin is None:
            move_subtree(Section, root, keep, None)
        else:
            merge_section(Section, root, twin)
    repoint(Project, gone, keep, skip=(Section,))
    if not keep.description and gone.description:
        keep.description = gone.description
        keep.save(update_fields=["description"])
    gone.delete()


def merge_projects(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Section = apps.get_model("core", "Section")
    groups: dict[str, list] = {}
    for project in Project.objects.order_by("pk"):
        groups.setdefault(" ".join(project.name.split()).casefold(), []).append(project)
    for projects in groups.values():
        if len(projects) < 2:
            continue
        keep = max(projects, key=lambda p: (usage(Project, Section, p), -p.pk))
        for gone in projects:
            if gone.pk != keep.pk:
                merge_project(Project, Section, gone, keep)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_section_names_without_attributes"),
    ]

    operations = [
        migrations.RunPython(merge_projects, migrations.RunPython.noop),
    ]
