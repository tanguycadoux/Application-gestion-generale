"""Les note parts deviennent des passages (#387), avec le texte sans projet (#385).

Un passage est une section telle qu'écrite, à sa place (`position`, lignes de début
et de fin, identifiant de son titre) ; son projet est facultatif. Comme la note
part, c'est un **index dérivé** de `Note.body` : rien n'est copié. La migration
crée les tables, supprime les anciennes, recrée l'index plein texte (`passage_search`
et sa vue `passage_vocab`, mêmes colonnes que `0040_notepart_search_words`), puis
**recalcule elle-même les passages de toutes les notes** (`reprocess`).

Le recalcul est, par exception, celui de l'application (`reprocess_notes`), et non
une copie figée : l'analyse d'une note est tout le parseur. Il ne vaut donc que si
le code de l'application correspond au schéma de cette migration ; sinon (une base
migrée bien plus tard, après d'autres changements des passages), il est abandonné
sans rien casser, et la migration demande de lancer `python manage.py
reprocess_notes`. Les tâches issues des notes ne dépendent pas des note parts
(identité : date, chemin et texte de la ligne, #240) : le recalcul les retrouve, et
crée celles des cases du texte sans projet, à revoir.

Retour en arrière : les tables des note parts reviennent vides, avec leur index ;
`reprocess_notes` du code d'alors les remplit.
"""

import io

import django.db.models.deletion
from django.core.management import call_command
from django.db import DatabaseError, migrations, models, transaction

TOKENIZE = "tokenize = 'unicode61 remove_diacritics 2'"


def search_tables(prefix: str) -> tuple[str, ...]:
    return (
        f"CREATE VIRTUAL TABLE {prefix}_search USING fts5("
        f"content, headings, words, {TOKENIZE})",
        f"CREATE VIRTUAL TABLE {prefix}_vocab USING fts5vocab({prefix}_search, 'col')",
    )


def drop_search_tables(prefix: str) -> tuple[str, ...]:
    return (f"DROP TABLE {prefix}_vocab", f"DROP TABLE {prefix}_search")


def reprocess(apps, schema_editor):
    """Recalcule les passages de toutes les notes, avec le code de l'application."""
    Note = apps.get_model("note_taking", "Note")
    if not Note.objects.exists():
        return
    output = io.StringIO()
    try:
        with transaction.atomic():
            call_command("reprocess_notes", stdout=output, stderr=output)
    except (DatabaseError, AttributeError, TypeError, ValueError) as error:
        print(
            "\n  Les passages n'ont pas pu être recalculés pendant la migration "
            f"({error}).\n  Lancer : python manage.py reprocess_notes"
        )
        return
    print(f"\n  Passages recalculés : {output.getvalue().strip()}")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_delete_subject"),
        ("images", "0002_copy_note_part_images"),
        ("note_taking", "0041_saved_search_filters"),
        # Le recalcul crée des tâches : leur schéma doit être celui d'aujourd'hui.
        ("todolist", "0021_task_note_fields_project_optional"),
    ]

    operations = [
        migrations.RunSQL(
            sql=drop_search_tables("note_part"),
            reverse_sql=search_tables("note_part"),
        ),
        migrations.CreateModel(
            name="Passage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0)),
                ("start_line", models.PositiveIntegerField(default=1)),
                ("end_line", models.PositiveIntegerField(default=1)),
                ("content", models.TextField(blank=True, default="")),
                ("heading_path", models.TextField(blank=True, default="")),
                (
                    "heading_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("anchor_path", models.TextField(blank=True, default="")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "note",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="passages",
                        to="note_taking.note",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="passages",
                        to="core.project",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="passages",
                        to="core.section",
                        verbose_name="chemin",
                    ),
                ),
                (
                    "tags",
                    models.ManyToManyField(
                        blank=True, related_name="passages", to="core.tag"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PassageImageLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="passage_links",
                        to="images.image",
                    ),
                ),
                (
                    "passage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="image_links",
                        to="note_taking.passage",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("passage", "image"), name="unique_passage_image"
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="passage",
            name="images",
            field=models.ManyToManyField(
                blank=True,
                related_name="passages",
                through="note_taking.PassageImageLink",
                to="images.image",
            ),
        ),
        migrations.RemoveField(model_name="notepart", name="images"),
        migrations.DeleteModel(name="NotePartImageLink"),
        migrations.DeleteModel(name="NotePart"),
        migrations.RunSQL(
            sql=search_tables("passage"),
            reverse_sql=drop_search_tables("passage"),
        ),
        migrations.RunPython(reprocess, migrations.RunPython.noop),
    ]
