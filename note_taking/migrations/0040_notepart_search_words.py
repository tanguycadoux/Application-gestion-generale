"""Formes réduites des mots dans l'index plein texte (#372).

Une table FTS5 ne prend pas de colonne de plus : la table est recréée avec une
troisième colonne, `words` (le texte et les titres à leur forme réduite, où singulier
et pluriel s'écrivent pareil). Les lignes de l'index existant sont reprises telles
quelles (`content`, `headings`) et reçoivent leur colonne `words` : rien à relancer
après la migration. Le vocabulaire (#200) devient une vue par colonne, pour ne lire
que les formes réduites.

Copie figée des règles de `note_taking/word_forms.py` et de `core.tables.fold` : une
migration n'importe pas le code de l'application.
"""

import re
import unicodedata

from django.db import migrations

TOKENIZE = "tokenize = 'unicode61 remove_diacritics 2'"
TOKEN_REGEX = re.compile(r"[^\W_]+")
MIN_LENGTH = 5


def fold(text):
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def reduce_word(word):
    if len(word) < MIN_LENGTH or not word.isalpha():
        return word
    if word.endswith("eaux"):
        return word[:-1]
    if word.endswith("aux"):
        return word[:-3] + "al"
    if word.endswith(("s", "x")):
        return word[:-1]
    return word


def reduce_text(text):
    return TOKEN_REGEX.sub(lambda match: reduce_word(match.group()), fold(text))


def words(content, headings):
    """La colonne `words` : le texte et les titres à leur forme réduite."""
    return reduce_text(f"{content or ''}\n{headings or ''}")


def recreate(cursor, columns, vocabulary):
    """Recrée l'index avec ces colonnes et y remet ses lignes ; renvoie les lignes."""
    cursor.execute("SELECT rowid, content, headings FROM note_part_search")
    rows = cursor.fetchall()
    cursor.execute("DROP TABLE note_part_vocab")
    cursor.execute("DROP TABLE note_part_search")
    cursor.execute(
        f"CREATE VIRTUAL TABLE note_part_search USING fts5({columns}, {TOKENIZE})"
    )
    cursor.execute(
        "CREATE VIRTUAL TABLE note_part_vocab "
        f"USING fts5vocab(note_part_search, '{vocabulary}')"
    )
    return rows


def add_words(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        rows = recreate(cursor, "content, headings, words", "col")
        cursor.executemany(
            "INSERT INTO note_part_search(rowid, content, headings, words) "
            "VALUES (%s, %s, %s, %s)",
            [
                (rowid, content, headings, words(content, headings))
                for rowid, content, headings in rows
            ],
        )


def remove_words(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        rows = recreate(cursor, "content, headings", "row")
        cursor.executemany(
            "INSERT INTO note_part_search(rowid, content, headings) "
            "VALUES (%s, %s, %s)",
            rows,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("note_taking", "0039_savedsearch"),
    ]

    operations = [
        migrations.RunPython(add_words, remove_words),
    ]
