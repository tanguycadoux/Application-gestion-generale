from django.db import migrations


class Migration(migrations.Migration):
    """Table FTS5 de l'index plein texte (#198). Elle démarre vide : `reprocess_notes`
    la remplit (index dérivé, voir `note_taking/search_index.py`)."""

    dependencies = [
        ("note_taking", "0036_alter_notepart_section"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE VIRTUAL TABLE note_part_search USING fts5("
                "content, headings, tokenize = 'unicode61 remove_diacritics 2')"
            ),
            reverse_sql="DROP TABLE note_part_search",
        ),
    ]
