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
