"""Liens vers d'autres notes (#206) dans le HTML rendu : `AAAA-MM-JJ#ancre` (ou
`AAAA-MM-JJ.qmd#ancre`)
mène à la page de la note ; une note absente est signalée, pas refusée."""

import re
from datetime import date

from django.urls import reverse
from django.utils.html import escape

from core.dates import date_text

# Balise ouvrante d'un lien du HTML filtré, dont l'adresse est le fichier d'une note.
NOTE_LINK_TAG_REGEX = re.compile(
    r'<a\b(?P<before>[^>]*?)\shref="(?P<date>\d{4}-\d{2}-\d{2})(?:\.qmd)?'
    r'(?P<anchor>#[^"]*)?"(?P<after>[^>]*)>'
)
# Titre et classes écrits, remplacés par ceux d'un lien cassé.
REPLACED_ATTRS_REGEX = re.compile(r'\s(?:title|class)="[^"]*"')

# Lien vers une note absente : souligné en pointillés, en rouge, et expliqué au
# survol. Il mène à la création de la note, à sa date.
MISSING_CLASSES = (
    "note-link-missing text-red-800 underline decoration-dotted underline-offset-2 "
    "hover:text-red-900"
)


def parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def resolve_note_links(html: str) -> str:
    """Fait mener chaque lien `AAAA-MM-JJ` (ou `.qmd`) à la page de la note, à son ancre.

    Le HTML est filtré : `<a` n'y est que le début d'un lien (pas dans du code,
    échappé). Une note absente garde son texte, marqué comme lien cassé.
    """
    matches = list(NOTE_LINK_TAG_REGEX.finditer(html))
    if not matches:
        return html
    # Import local : les modèles importent le rendu.
    from ..models import Note

    days = {day for match in matches if (day := parse_day(match["date"]))}
    existing = set(Note.objects.filter(date__in=days).values_list("date", flat=True))

    def repl(match: re.Match[str]) -> str:
        before, after = match["before"], match["after"]
        day = parse_day(match["date"])
        if day in existing:
            url = reverse("note_taking:note_detail", args=[day])
            return f'<a{before} href="{url}{match["anchor"] or ""}"{after}>'
        attrs = REPLACED_ATTRS_REGEX.sub("", before + after)
        if day is None:
            title = f"« {match['date']} » n'est pas une date : aucune note."
            return f'<a{attrs} class="{MISSING_CLASSES}" title="{escape(title)}">'
        title = f"Aucune note le {date_text(day, 'moyen')} : cliquer pour la créer."
        url = f"{reverse('note_taking:new_note')}?date={day.isoformat()}"
        return (
            f'<a{attrs} href="{escape(url)}" class="{MISSING_CLASSES}" '
            f'title="{escape(title)}">'
        )

    return NOTE_LINK_TAG_REGEX.sub(repl, html)
