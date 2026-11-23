"""Projets retrouvés par leur nom, casse ignorée (#374), comme les niveaux.

« Chantier nord » écrit dans une note retrouve « Chantier Nord » : un projet garde
la casse de sa première écriture. La comparaison se fait en Python : le `LOWER` de
SQLite ne replie que l'ASCII, pas « É ».
"""

from .models import Project, Section


def clean_name(name: str) -> str:
    return " ".join(name.split())


def project_named(name: str, exclude: int | None = None) -> Project | None:
    """Le projet de ce nom, casse et espaces ignorés (sauf celui de clé `exclude`) ;
    None s'il n'existe pas."""
    wanted = clean_name(name).casefold()
    return next(
        (
            project
            for project in Project.objects.all()
            if project.pk != exclude and clean_name(project.name).casefold() == wanted
        ),
        None,
    )


def project_for(name: str) -> tuple[Project, bool]:
    """Le projet de ce nom, créé s'il n'existe pas ; et s'il vient d'être créé."""
    found = project_named(name)
    if found is not None:
        return found, False
    return Project.objects.create(name=clean_name(name)), True


def check_new_project_name(project: Project, raw: str) -> tuple[str, str]:
    """(nom nettoyé, erreur) pour renommer ce projet (#170) ; l'erreur est vide si
    le nom convient. Un simple changement de casse est permis ; le nom d'un autre
    projet ne l'est pas : réunir deux projets est un autre parcours."""
    name = clean_name(raw)
    longest = Project._meta.get_field("name").max_length or 200
    if not name:
        return name, "Écrivez le nouveau nom."
    if len(name) > longest:
        return name, f"Un nom de projet ne dépasse pas {longest} caractères."
    if name == project.name:
        return name, "C'est déjà son nom."
    other = project_named(name, exclude=project.pk)
    if other is not None:
        return name, (
            f"Un projet « {other.name} » existe déjà : renommer un projet avec le nom "
            "d'un autre n'est pas possible depuis cette page."
        )
    return name, ""


def _reverse_relations(include_hidden: bool):
    """Ce qui pointe vers un projet, hors niveaux : passages, tâches, et (cachées)
    les cases des recherches enregistrées."""
    return [
        relation
        for relation in Project._meta.get_fields(include_hidden=include_hidden)
        if relation.auto_created
        and not relation.concrete
        and relation.related_model is not Section
    ]


def merge_projects(gone: Project, keep: Project) -> None:
    """`gone` rejoint `keep` (#170) : ses niveaux passent sous `keep`, ceux de même
    nom (casse ignorée) réunis avec leurs homonymes ; ce qui pointe vers lui
    (passages, tâches, recherches enregistrées) passe à `keep`. `keep` garde son
    nom, sa couleur, et sa description, ou prend celle de `gone` s'il n'en a pas.
    `gone` est supprimé."""
    from .sections import merge_section, with_descendants

    for root in list(Section.objects.filter(project=gone, parent=None)):
        twin = next(
            (
                section
                for section in Section.objects.filter(project=keep, parent=None)
                if clean_name(section.name).casefold()
                == clean_name(root.name).casefold()
            ),
            None,
        )
        below = with_descendants({root.pk}) - {root.pk}
        Section.objects.filter(pk__in=below).update(project=keep)
        if twin is None:
            Section.objects.filter(pk=root.pk).update(project=keep)
        else:
            root.refresh_from_db()
            merge_section(root, twin)
    for relation in _reverse_relations(include_hidden=True):
        name = relation.field.name
        related = relation.related_model._base_manager
        if relation.one_to_many:
            related.filter(**{name: gone}).update(**{name: keep})
        elif relation.many_to_many:
            for obj in related.filter(**{name: gone}):
                getattr(obj, name).remove(gone)
                getattr(obj, name).add(keep)
    if not keep.description and gone.description:
        keep.description = gone.description
        keep.save(update_fields=["description"])
    gone.delete()


def forget_project_if_unused(project: Project | None) -> bool:
    """Supprime ce projet si plus rien ne l'utilise (niveaux, passages, tâches) ;
    renvoie s'il l'a été. Une case de recherche enregistrée ne le retient pas."""
    if project is None or project.sections.exists():
        return False
    for relation in _reverse_relations(include_hidden=False):
        name = relation.field.name
        if relation.related_model._base_manager.filter(**{name: project}).exists():
            return False
    project.delete()
    return True
