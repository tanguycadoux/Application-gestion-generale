"""Index plein texte des note parts (#198) : une table FTS5 de SQLite.

C'est un index **dérivé** : il se recalcule avec les note parts (enregistrement,
suppression, `reprocess_notes`) et ne contient rien qu'on ne puisse reconstruire.
Une ligne par note part, dont le `rowid` est la clé de la note part ; on y met le
texte de la note part et ses titres. Les blocs `{.metadata}` (déjà cherchables par
tag) et les références `image:<pk>` n'y sont pas.

La table (migration `RunSQL`) ignore la casse et les accents (`unicode61
remove_diacritics 2`). Ce module ne connaît que `NotePart` : les filtres de projet,
de chemin et de tag restent ceux du modèle.
"""

import re

from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import NotePart
from .qmd.parser import METADATA_BLOCK_START

TABLE = "note_part_search"

# `(image:12)` et les attributs `{width=50%}` qui le suivent ; la légende reste.
IMAGE_REFERENCE_REGEX = re.compile(r"\(image:\d+\)(\{[^}]*\})?")


def indexed_text(content: str) -> str:
    """Le texte d'une note part qu'on met dans l'index."""
    lines = []
    in_metadata = False
    for line in content.splitlines():
        stripped = line.strip()
        if in_metadata:
            in_metadata = stripped != ":::"
        elif stripped == METADATA_BLOCK_START:
            in_metadata = True
        else:
            lines.append(line)
    return IMAGE_REFERENCE_REGEX.sub("", "\n".join(lines))


def quote(text: str) -> str:
    """Un mot ou une phrase de FTS5 entre guillemets : aucun opérateur interprété."""
    return '"' + text.replace('"', '""') + '"'


def match_expression(text: str) -> str | None:
    """Requête FTS5 d'un texte libre : chaque mot est une phrase entre guillemets.

    Les mots sont tous requis ; aucun opérateur de FTS5 (`OR`, `NEAR`, `*`, `:`,
    parenthèses) n'est interprété, donc un texte quelconque ne peut pas être une
    requête mal formée. Renvoie `None` s'il n'y a aucun mot.
    """
    words = text.split()
    if not words:
        return None
    return " ".join(quote(word) for word in words)


def match_parts(expression: str) -> list[int]:
    """Clés des note parts qui répondent à une requête FTS5, la plus pertinente d'abord."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT rowid FROM {TABLE} WHERE {TABLE} MATCH %s ORDER BY rank",
            [expression],
        )
        return [row[0] for row in cursor.fetchall()]


def search_parts(text: str) -> list[int]:
    """Clés des note parts qui contiennent tous les mots, la plus pertinente d'abord."""
    expression = match_expression(text)
    return [] if expression is None else match_parts(expression)


def index_part(part: NotePart) -> None:
    unindex_part(part.pk)
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABLE}(rowid, content, headings) VALUES (%s, %s, %s)",
            [part.pk, indexed_text(part.content), part.heading_path],
        )


def unindex_part(pk: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE} WHERE rowid = %s", [pk])


def rebuild_index() -> int:
    """Vide l'index puis y remet toutes les note parts. Renvoie leur nombre."""
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE}")
    count = 0
    for part in NotePart.objects.only("pk", "content", "heading_path").iterator():
        index_part(part)
        count += 1
    return count


@receiver(post_save, sender=NotePart)
def index_saved_part(sender, instance, raw=False, **kwargs):
    if not raw:
        index_part(instance)


@receiver(post_delete, sender=NotePart)
def unindex_deleted_part(sender, instance, **kwargs):
    unindex_part(instance.pk)
