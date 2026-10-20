"""Export des notes en fichiers qmd, réunis dans une archive zip (#64).

L'archive reprend la disposition d'un dossier Quarto : AAAA-MM-JJ.qmd à la
racine, images/<nom> à côté. Dézippée, elle forme un projet Quarto valide.
"""

import re
import zipfile
from pathlib import PurePosixPath
from typing import IO

from images.models import Image

from ..models import Note
from ..rendering import EXTERNAL_URL_REGEX, IMAGE_PATH_REGEX
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
        path = match.group("path")
        if EXTERNAL_URL_REGEX.match(path):
            return match.group(0)
        name = PurePosixPath(path.replace("\\", "/")).name
        return match.group(0).replace(path, f"{IMAGES_DIR}/{name}")

    return IMAGE_PATH_REGEX.sub(repl, body)


def write_notes_archive(output: IO[bytes]) -> None:
    """Écrit dans `output` l'archive de toutes les notes et de toutes les images."""
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for note in Note.objects.order_by("date"):
            archive.writestr(f"{note.date}.qmd", note_to_qmd(note).encode("utf-8"))
        for image in Image.objects.order_by("name"):
            if not image.file:
                continue
            with image.file.open("rb") as file:
                archive.writestr(f"{IMAGES_DIR}/{image.name}", file.read())
