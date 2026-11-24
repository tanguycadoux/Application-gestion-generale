"""Les notes d'une semaine, groupées par projet, pour son bilan (#208)."""

from dataclasses import dataclass, field

from django.urls import reverse

from core.models import Project
from core.sections import LABEL_SEPARATOR
from core.tables import fold
from core.weeks import Week

from .models import Note, Passage
from .qmd.parser import heading_name
from .search_document import split_titles
from .search_index import indexed_text


@dataclass
class WeekNote:
    """Une note sous un projet : l'adresse de son premier titre de ce projet, et
    celle de chaque chemin qu'elle y écrit."""

    note: Note
    url: str
    paths: dict[str, str] = field(default_factory=dict)


@dataclass
class ProjectNotes:
    """`project` vide : le texte sans projet (#385), et les notes vides."""

    project: Project | None
    notes: list[WeekNote] = field(default_factory=list)


def week_notes(week: Week) -> dict:
    """Les projets par nom, le texte sans projet à la fin ; les notes d'un projet par
    date, leurs chemins dans l'ordre écrit. Deux requêtes, leurs passages compris."""
    notes = list(Note.objects.filter(date__range=(week.monday, week.sunday)))
    passages = (
        Passage.objects.filter(note__in=notes)
        .select_related("note", "project")
        .order_by("note__date", "position")
    )
    groups: dict[int | None, ProjectNotes] = {}
    entries: dict[tuple[int | None, int], WeekNote] = {}

    def entry(project: Project | None, note: Note, anchor: str) -> WeekNote:
        key = project.pk if project else None
        if (key, note.pk) not in entries:
            found = WeekNote(note, note_url(note, anchor))
            entries[key, note.pk] = found
            groups.setdefault(key, ProjectNotes(project)).notes.append(found)
        return entries[key, note.pk]

    for passage in passages:
        anchors = passage.anchor_path.split()
        found = entry(passage.project, passage.note, anchors[0] if anchors else "")
        titles = [heading_name(title) for title in split_titles(passage.heading_path)]
        # Le premier titre est celui du projet, affiché au-dessus.
        path = LABEL_SEPARATOR.join(titles[1:] if passage.project else titles)
        # Un niveau sans texte n'est que le parent de ceux qu'il contient.
        if path and indexed_text(passage.content).strip():
            found.paths.setdefault(path, note_url(passage.note, passage.heading_id))

    written = {note_pk for _, note_pk in entries}
    for note in notes:
        if note.pk not in written:
            entry(None, note, "")
    for group in groups.values():
        group.notes.sort(key=lambda found: found.note.date)
    return {
        "groups": sorted(
            groups.values(),
            key=lambda group: (
                group.project is None,
                fold(group.project.name) if group.project else "",
            ),
        )
    }


def note_url(note: Note, anchor: str) -> str:
    url = reverse("note_taking:note_detail", args=[note.date])
    return f"{url}#{anchor}" if anchor else url
