from django.db import migrations, models

# Copie figée des familles de core.models.PROJECT_COLORS (#162) : une migration
# n'importe pas le code de l'application, qui peut évoluer.
COLORS = [
    "orange",
    "yellow",
    "lime",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
]


def assign_colors(apps, schema_editor):
    """Une couleur par projet existant, dans l'ordre alphabétique des projets."""
    Project = apps.get_model("core", "Project")
    for index, project in enumerate(Project.objects.order_by("name")):
        project.color = COLORS[index % len(COLORS)]
        project.save(update_fields=["color"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_subject_tag"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="color",
            field=models.CharField(
                choices=[
                    ("orange", "Orange"),
                    ("yellow", "Jaune"),
                    ("lime", "Citron vert"),
                    ("emerald", "Émeraude"),
                    ("teal", "Sarcelle"),
                    ("cyan", "Cyan"),
                    ("sky", "Ciel"),
                    ("indigo", "Indigo"),
                    ("violet", "Violet"),
                    ("purple", "Pourpre"),
                    ("fuchsia", "Fuchsia"),
                    ("pink", "Rose"),
                    ("rose", "Framboise"),
                ],
                default="",
                max_length=20,
                verbose_name="couleur",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
