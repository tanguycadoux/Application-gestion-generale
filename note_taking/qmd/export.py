"""Export des notes en fichiers qmd, réunis dans une archive zip (#64).

L'archive reprend la disposition d'un dossier Quarto : AAAA-MM-JJ.qmd à la
racine, images/<nom> à côté. Dézippée, elle forme un projet Quarto valide.
"""

import re
import zipfile
from collections.abc import Iterable
from typing import IO

from images.models import Image

from ..models import Note
from ..rendering import IMAGE_PATH_REGEX, image_name
from .parser import FRONT_MATTER_DELIMITER

IMAGES_DIR = "images"


def note_to_qmd(note: Note) -> str:
    """Contenu du fichier qmd d'une note : bloc d'en-tête régénéré, puis le corps.

    Le bloc d'en-tête reprend les fins de ligne du corps (Windows ou Unix), pour
    que l'import redonne exactement le même corps.
    """
    newline = "\r\n" if "\r\n" in note.body else "\n"
    header = newline.join(
        [FRONT_MATTER_DELIMITER, f"date: {note.date}", FRONT_MATTER_DELIMITER, "", ""]
    )
    return header + normalize_image_paths(note.body)


def normalize_image_paths(body: str) -> str:
    """Ramène chaque chemin d'image à images/<nom>, sauf les URL externes."""

    def repl(match: re.Match[str]) -> str:
        name = image_name(match.group("path"))
        if name is None:
            return match.group(0)
        return match.group(0).replace(match.group("path"), f"{IMAGES_DIR}/{name}")

    return IMAGE_PATH_REGEX.sub(repl, body)


def write_notes_archive(output: IO[bytes]) -> None:
    """Écrit dans `output` l'archive de toutes les notes et de toutes les images."""
    write_archive(output, Note.objects.order_by("date"), Image.objects.order_by("name"))


def write_note_archive(note: Note, output: IO[bytes]) -> None:
    """Écrit dans `output` l'archive d'une note et des images qu'elle référence.

    Les images sont celles nommées dans le corps, comme dans le fichier qmd,
    y compris pour une note dont l'analyse a échoué.
    """
    names = {
        image_name(match.group("path"))
        for match in IMAGE_PATH_REGEX.finditer(note.body)
    }
    names.discard(None)
    write_archive(output, [note], Image.objects.filter(name__in=names).order_by("name"))


def write_archive(output: IO[bytes], notes: Iterable[Note], images: Iterable[Image]):
    """Archive zip à la disposition d'un dossier Quarto : qmd à la racine, images/."""
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for note in notes:
            archive.writestr(f"{note.date}.qmd", note_to_qmd(note).encode("utf-8"))
        for image in images:
            if not image.file:
                continue
            with image.file.open("rb") as file:
                archive.writestr(f"{IMAGES_DIR}/{image.name}", file.read())
