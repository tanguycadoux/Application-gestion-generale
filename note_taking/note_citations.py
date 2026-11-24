"""Notes qui citent une note (#207) : les passages dont un lien
`[texte](AAAA-MM-JJ.qmd)` mène à elle (`PassageNoteLink`), pour sa page."""

from dataclasses import dataclass

from django.urls import reverse

from .excerpts import plain_line
from .models import Note, Passage, PassageNoteLink
from .qmd.links import NOTE_LINK_REGEX, without_code
from .qmd.parser import HEADING_SEPARATOR


@dataclass
class Citation:
    passage: Passage
    # Adresse du passage qui cite : la page de sa note, à l'ancre de son titre.
    url: str
    excerpt: str

    @property
    def path(self) -> str:
        """Les titres du passage sous son projet, affiché à part : « Réunion ›
        Ordre du jour »."""
        return HEADING_SEPARATOR.join(
            self.passage.heading_path.split(HEADING_SEPARATOR)[1:]
        )


def excerpt(content: str, day: str) -> str:
    """La ligne du passage qui contient le lien vers la note du jour `day`, en
    texte, raccourcie."""
    lines = without_code(content).splitlines()
    line = next(
        (
            text
            for text in lines
            if any(m["date"] == day for m in NOTE_LINK_REGEX.finditer(text))
        ),
        "",
    )
    return plain_line(line)


def citations(note: Note) -> list[Citation]:
    """Les passages des autres notes qui citent celle-ci, des plus récents aux plus
    anciens, dans l'ordre écrit ; un passage qui la cite plusieurs fois une seule."""
    links = (
        PassageNoteLink.objects.filter(target_date=note.date)
        .exclude(passage__note=note)
        .select_related("passage__note", "passage__project")
        .order_by("-passage__note__date", "passage__position")
    )
    found: dict[int, Citation] = {}
    for link in links:
        passage = link.passage
        if passage.pk in found:
            continue
        url = reverse("note_taking:note_detail", args=[passage.note.date])
        if passage.heading_id:
            url += f"#{passage.heading_id}"
        found[passage.pk] = Citation(
            passage, url, excerpt(passage.content, str(note.date))
        )
    return list(found.values())
