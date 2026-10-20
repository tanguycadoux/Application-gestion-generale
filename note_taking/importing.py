"""Import unifié : notes qmd, images et archives de l'export (#114).

Chaque fichier sélectionné est traité selon son type :

- `.zip` : archive de l'export, à la disposition d'un dossier Quarto
  (AAAA-MM-JJ.qmd à la racine, images/<nom>) ;
- `.qmd` : une note ;
- image (`.png`, `.jpg`, `.svg`…) : une image ;
- autre : non reconnu.

Les images sont importées avant les notes, qui les citent. La base fait foi :
une image déjà présente sous ce nom est gardée (le fichier importé est écarté,
sans doublon), une note dont la date existe déjà est ignorée, jamais remplacée.
"""

import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from django.core.files.base import ContentFile, File

from core.exceptions import AppError
from images.models import Image
from images.services import import_image

from .exceptions import NoteAlreadyExistsError
from .models import Note
from .qmd.export import IMAGES_DIR
from .services import insert_note_in_table

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


@dataclass
class ImportReport:
    created: list[Note] = field(default_factory=list)
    # Notes déjà en base à la date d'un fichier importé, laissées intactes.
    skipped: list[Note] = field(default_factory=list)
    # (nom du fichier, message d'erreur)
    failed: list[tuple[str, str]] = field(default_factory=list)
    images_imported: list[str] = field(default_factory=list)
    # Images déjà en base sous ce nom : gardées, le fichier importé est écarté.
    images_kept: list[str] = field(default_factory=list)
    # Fichiers ni note, ni image, ni archive (ou mal placés dans une archive).
    ignored: list[str] = field(default_factory=list)


def import_files(files: Iterable[File]) -> ImportReport:
    """Importe les fichiers sélectionnés selon leur type ; voir le module."""
    report = ImportReport()
    notes: list[File] = []
    images: list[File] = []

    for file in files:
        suffix = PurePosixPath(file.name or "").suffix.lower()
        if suffix == ".zip":
            read_archive(file, notes, images, report)
        elif suffix == ".qmd":
            notes.append(file)
        elif suffix in IMAGE_EXTENSIONS:
            images.append(file)
        else:
            report.ignored.append(file.name or "")

    for image in sorted(images, key=lambda f: f.name or ""):
        name = PurePosixPath(image.name or "").name
        if Image.objects.filter(name=name).exists():
            report.images_kept.append(name)
        else:
            import_image(image)
            report.images_imported.append(name)

    for note_file in sorted(notes, key=lambda f: f.name or ""):
        name = note_file.name or ""
        try:
            note = insert_note_in_table(note_file)
        except NoteAlreadyExistsError:
            report.skipped.append(Note.objects.get(date=PurePosixPath(name).stem))
        except AppError as e:
            report.failed.append((name, str(e)))
        else:
            report.created.append(note)

    return report


def read_archive(
    file: File, notes: list[File], images: list[File], report: ImportReport
) -> None:
    """Répartit les entrées d'une archive de l'export en notes et images."""
    try:
        archive = zipfile.ZipFile(file)
    except zipfile.BadZipFile:
        report.failed.append((file.name or "", "Ce n'est pas une archive zip valide."))
        return

    for entry in archive.infolist():
        if entry.is_dir():
            continue
        path = PurePosixPath(entry.filename)
        if len(path.parts) == 1 and path.suffix == ".qmd":
            notes.append(ContentFile(archive.read(entry), name=entry.filename))
        elif len(path.parts) == 2 and path.parts[0] == IMAGES_DIR:
            images.append(ContentFile(archive.read(entry), name=path.name))
        else:
            report.ignored.append(f"{file.name}/{entry.filename}")
