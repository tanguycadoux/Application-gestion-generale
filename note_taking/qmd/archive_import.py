"""Réimport d'une archive de notes produite par l'export (#114).

L'archive a la disposition d'un dossier Quarto : AAAA-MM-JJ.qmd à la racine,
images/<nom> à côté. La base fait foi : une note dont la date existe déjà est
ignorée, jamais remplacée, et une image déjà présente sous ce nom est gardée.
"""

import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from django.core.files.base import ContentFile

from core.exceptions import AppError
from images.models import Image
from images.services import import_image

from ..exceptions import InvalidArchiveError, NoteAlreadyExistsError
from ..models import Note
from ..services import insert_note_in_table
from .export import IMAGES_DIR


@dataclass
class ArchiveImportReport:
    created: list[Note] = field(default_factory=list)
    # Notes déjà en base à la date d'un fichier de l'archive, laissées intactes.
    skipped: list[Note] = field(default_factory=list)
    # (nom du fichier, message d'erreur)
    failed: list[tuple[str, str]] = field(default_factory=list)
    images_imported: list[str] = field(default_factory=list)
    images_kept: list[str] = field(default_factory=list)
    # Entrées de l'archive qui ne sont ni une note ni une image.
    ignored: list[str] = field(default_factory=list)


def import_notes_archive(file) -> ArchiveImportReport:
    """Importe les images absentes, puis les notes nouvelles, d'une archive zip."""
    try:
        archive = zipfile.ZipFile(file)
    except zipfile.BadZipFile:
        raise InvalidArchiveError(
            "Le fichier n'est pas une archive zip valide."
        ) from None

    report = ArchiveImportReport()
    notes, images = [], []
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        path = PurePosixPath(entry.filename)
        if len(path.parts) == 1 and path.suffix == ".qmd":
            notes.append(entry)
        elif len(path.parts) == 2 and path.parts[0] == IMAGES_DIR:
            images.append(entry)
        else:
            report.ignored.append(entry.filename)

    # Les images d'abord : l'analyse des notes a besoin de celles qu'elles citent.
    for entry in sorted(images, key=lambda e: e.filename):
        name = PurePosixPath(entry.filename).name
        if Image.objects.filter(name=name).exists():
            report.images_kept.append(name)
        else:
            import_image(ContentFile(archive.read(entry), name=name))
            report.images_imported.append(name)

    for entry in sorted(notes, key=lambda e: e.filename):
        try:
            note = insert_note_in_table(
                ContentFile(archive.read(entry), name=entry.filename)
            )
        except NoteAlreadyExistsError:
            note_date = PurePosixPath(entry.filename).stem
            report.skipped.append(Note.objects.get(date=note_date))
        except AppError as e:
            report.failed.append((entry.filename, str(e)))
        else:
            report.created.append(note)

    return report
