"""Le nom d'un niveau est le texte du titre sans ses attributs Pandoc (#367).

Avant, `## Réunion de chantier {#reu-12}` donnait le niveau « Réunion de chantier
{#reu-12} », distinct de « Réunion de chantier ». La migration retire les attributs
du nom des niveaux existants (même règle que le parseur, copiée ici) :

- un niveau dont un frère (même projet, même parent) porte déjà ce nom, casse
  ignorée, **le rejoint** : le niveau gardé est celui qui n'avait pas d'attributs
  (son nom, sa casse) ; ce qui utilisait l'autre (passages, tâches, recherches
  enregistrées) passe au niveau gardé, et ses sous-niveaux le rejoignent, ceux de
  même nom, casse ignorée, réunis à leur tour ;
- deux niveaux frères qui ne diffèrent que par leurs attributs, sans frère nu,
  deviennent un seul : le plus ancien (plus petite clé), renommé ;
- sinon, le niveau est simplement renommé.

Rien n'est à recalculer : les titres des notes ne changent pas (`heading_path`, et
donc l'identité des tâches, #240, gardent les attributs) ; les passages pointent
déjà sur le niveau gardé.

`core` ne connaît pas les apps : ce qui utilise un niveau est lu sur le modèle (clés
étrangères et relations plusieurs-à-plusieurs qui y mènent), comme
`forget_unused_sections`. Pas de retour en arrière : les attributs retirés ne
reviennent pas (ils sont toujours écrits dans les notes).
"""

import re

from django.db import migrations

TITLE_ATTRIBUTES_REGEX = re.compile(r"\s*\{[^}]*\}\s*$")


def heading_name(title: str) -> str:
    return TITLE_ATTRIBUTES_REGEX.sub("", title).strip() or title.strip()


def repoint(model, gone, keep) -> None:
    """Ce qui mène à `gone` (hors parent d'un niveau) mène désormais à `keep`."""
    for relation in model._meta.related_objects:
        if relation.related_model is model:
            continue
        name = relation.field.name
        related = relation.related_model._base_manager
        if relation.one_to_many:
            related.filter(**{name: gone}).update(**{name: keep})
        elif relation.many_to_many:
            for obj in related.filter(**{name: gone}):
                getattr(obj, name).remove(gone)
                getattr(obj, name).add(keep)


def child_named(Section, project_id, parent, name):
    for sibling in Section.objects.filter(project_id=project_id, parent=parent):
        if sibling.name.casefold() == name.casefold():
            return sibling
    return None


def merge_section(Section, gone, keep) -> None:
    """`gone` rejoint `keep` : ses sous-niveaux de même nom (casse ignorée) sont
    réunis à leur tour, les autres passent sous `keep`."""
    for child in list(Section.objects.filter(parent=gone)):
        twin = child_named(Section, keep.project_id, keep, child.name)
        if twin is None:
            child.parent = keep
            child.save(update_fields=["parent"])
        else:
            merge_section(Section, child, twin)
    repoint(Section, gone, keep)
    gone.delete()


def depth(Section, section) -> int:
    count = 0
    while section.parent_id is not None:
        section = Section.objects.get(pk=section.parent_id)
        count += 1
    return count


def strip_attributes(apps, schema_editor):
    Section = apps.get_model("core", "Section")
    while True:
        pending = [
            section
            for section in Section.objects.order_by("pk")
            if heading_name(section.name) != section.name
        ]
        if not pending:
            return
        # Les parents d'abord : une fusion emporte les sous-niveaux.
        section = min(pending, key=lambda s: (depth(Section, s), s.pk))
        name = heading_name(section.name)
        siblings = [
            sibling
            for sibling in Section.objects.filter(
                project_id=section.project_id, parent_id=section.parent_id
            )
            .exclude(pk=section.pk)
            .order_by("pk")
            if heading_name(sibling.name).casefold() == name.casefold()
        ]
        bare = next((s for s in siblings if s.name == heading_name(s.name)), None)
        if bare is not None:
            merge_section(Section, section, bare)
            continue
        # Frères à attributs seulement : le plus ancien est gardé, renommé.
        keep = min([section, *siblings], key=lambda s: s.pk)
        keep.name = name
        keep.save(update_fields=["name"])
        for other in siblings + [section]:
            if other.pk != keep.pk:
                merge_section(Section, other, keep)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_delete_subject"),
        # Ce qui utilise un niveau doit être dans l'état des modèles.
        ("note_taking", "0042_passages"),
        ("todolist", "0021_task_note_fields_project_optional"),
    ]

    operations = [
        migrations.RunPython(strip_attributes, migrations.RunPython.noop),
    ]
