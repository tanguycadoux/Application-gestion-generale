"""Services de note : import, mise à jour, passages et images."""

from datetime import date

from django.db import transaction

from core.models import Project, Section, Tag
from core.projects import project_for
from core.sections import forget_unused_sections, section_for, similar_warnings
from images.models import Image

from .exceptions import (
    ImageNotFoundError,
    InvalidNoteFileError,
    NoteAlreadyExistsError,
    NoteParseError,
)
from .models import Note, Passage
from .qmd.files import check_metadata_date, read_note_file, split_front_matter
from .qmd.parser import HEADING_SEPARATOR, ParsedNote, parse_note
from .rendering import IMAGE_PATH_REGEX, image_name, note_heading_ids
from .signals import NoteFollowUp, passages_processed


@transaction.atomic
def update_note_from_source_file(note: Note, file) -> Note:
    note_date, content = read_note_file(file)
    metadata, body = split_front_matter(content)
    check_metadata_date(note_date, metadata)

    if str(note.date) != note_date:
        raise InvalidNoteFileError(
            "Le fichier source ne correspond pas à la date de la note."
        )

    note.body = body
    note.save()

    process_passages(note)
    return note


@transaction.atomic
def insert_note_in_table(file) -> Note:
    note_date, content = read_note_file(file)
    metadata, body = split_front_matter(content)
    check_metadata_date(note_date, metadata)

    if Note.objects.filter(date=note_date).exists():
        raise NoteAlreadyExistsError(f"Une note existe déjà pour le {note_date}.")

    note = Note.objects.create(date=date.fromisoformat(note_date), body=body)

    process_passages(note)
    return note


@transaction.atomic
def process_passages(
    note: Note, parsed_note: ParsedNote | None = None
) -> list[Passage]:
    """(Re)génère les passages à partir de note.body, puis émet passages_processed.

    À appeler après chaque sauvegarde de note.body (import fichier ou
    édition depuis le formulaire web), une fois `note` déjà persistée.
    Tout ou rien (#221) : en cas d'erreur, les passages et les tâches d'avant
    restent intacts ; le texte de la note, déjà enregistré, n'est pas annulé.
    """
    if parsed_note is None:
        parsed_note = parse_note(str(note.date), note.body)

        parsed_date = parsed_note.metadata.get("date")
        if parsed_date and str(note.date) != parsed_date:
            raise NoteParseError(
                "La date dans les métadonnées du contenu ne correspond pas "
                "à la date de la note."
            )

    # Pour signaler un projet ou un niveau créé à côté d'un nom proche (#374).
    known_projects = set(Project.objects.values_list("pk", flat=True))
    known_sections = set(Section.objects.values_list("pk", flat=True))
    note.passages.all().delete()
    passages = insert_passages(note, parsed_note)

    # Les stubs de Django typent les réponses en `str | None` : ce sont des objets.
    responses: list[object] = [
        response
        for _, response in passages_processed.send(
            sender=Note, note=note, passages=passages
        )
    ]
    note.follow_ups = tuple(
        response for response in responses if isinstance(response, NoteFollowUp)
    )
    note.warnings = (
        *parsed_note.warnings,
        *similar_warnings(known_projects, known_sections),
    )
    # Les sections qu'aucun passage ni tâche n'utilise plus sont oubliées (#295).
    forget_unused_sections()

    return passages


def insert_passages(note: Note, parsed_note: ParsedNote) -> list[Passage]:
    """Enregistre les passages analysés, dans l'ordre, avec l'identifiant de leurs
    titres dans la page de la note (#387). Le texte sans projet n'a ni projet ni
    chemin (#385)."""
    ids = note_heading_ids(note.body, parsed_note.headings)
    passages = []
    for position, parsed in enumerate(parsed_note.passages):
        content, images = replace_image_paths("\n".join(parsed.lines))

        # Un projet connu, quelle que soit sa casse, est repris (#374).
        project = project_for(parsed.project)[0] if parsed.project is not None else None
        section = section_for(project, parsed.path) if project else None
        anchors = [ids[number] for number in parsed.heading_numbers]

        passage = Passage.objects.create(
            note=note,
            position=position,
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            project=project,
            section=section,
            content=content,
            heading_path=HEADING_SEPARATOR.join(parsed.headings),
            heading_id=anchors[-1] if anchors else "",
            anchor_path=" ".join(anchors),
        )
        passage.tags.set(
            [Tag.objects.get_or_create(name=name)[0] for name in parsed.tags]
        )
        passage.images.set(images)
        passages.append(passage)
    return passages


def replace_image_paths(content: str) -> tuple[str, list[Image]]:
    """Remplace les chemins d'images par `image:<pk>`.

    Renvoie le contenu modifié et les images référencées, sans doublon.
    """
    images: dict[int, Image] = {}

    def repl(match):
        path = match.group("path")
        name = image_name(path)
        if name is None:
            # URL externe : pas une image importée, affichée en lien (#220).
            return match.group(0)

        try:
            image_obj = Image.objects.get(name=name)
        except Image.DoesNotExist:
            raise ImageNotFoundError(
                f"L'image {name} n'a pas été importée : l'importer avant la note."
            ) from None

        images[image_obj.pk] = image_obj
        return match.group(0).replace(path, f"image:{image_obj.pk}")

    return IMAGE_PATH_REGEX.sub(repl, content), list(images.values())
