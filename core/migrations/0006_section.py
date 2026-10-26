"""Les sections : niveaux d'un chemin sous un projet (#287, #295).

Elles remplacent les sujets, qui ne dépendaient d'aucun projet : les notes et les
tâches y passent dans leurs propres migrations, puis `0007` supprime `Subject`.
"""

import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_clear_project_descriptions"),
    ]

    operations = [
        migrations.CreateModel(
            name="Section",
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
                ("name", models.CharField(max_length=200, verbose_name="nom")),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="core.section",
                        verbose_name="niveau parent",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sections",
                        to="core.project",
                        verbose_name="projet",
                    ),
                ),
            ],
            options={
                "verbose_name": "section",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="section",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("project"),
                condition=models.Q(("parent__isnull", True)),
                name="unique_root_section",
            ),
        ),
        migrations.AddConstraint(
            model_name="section",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("parent"),
                condition=models.Q(("parent__isnull", False)),
                name="unique_child_section",
            ),
        ),
    ]
