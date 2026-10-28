from django.db import migrations


class Migration(migrations.Migration):
    """Vocabulaire de l'index plein texte (#200) : les mots de l'index et le nombre
    de note parts qui les contiennent, pour proposer les mots proches d'une faute
    de frappe. Une vue sur l'index, rien à remplir."""

    dependencies = [
        ("note_taking", "0037_notepart_search_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE VIRTUAL TABLE note_part_vocab "
                "USING fts5vocab(note_part_search, 'row')"
            ),
            reverse_sql="DROP TABLE note_part_vocab",
        ),
    ]
