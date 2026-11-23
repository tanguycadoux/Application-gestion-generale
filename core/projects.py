"""Projets retrouvés par leur nom, casse ignorée (#374), comme les niveaux.

« Chantier nord » écrit dans une note retrouve « Chantier Nord » : un projet garde
la casse de sa première écriture. La comparaison se fait en Python : le `LOWER` de
SQLite ne replie que l'ASCII, pas « É ».
"""

from .models import Project


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
