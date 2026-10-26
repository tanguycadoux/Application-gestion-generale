"""Vide les descriptions de projets identiques à leur nom (#243).

Reprises de l'ancien modèle lors de la fusion des projets (#19), elles faisaient
afficher chaque nom deux fois. Les autres descriptions sont gardées ; la casse
compte, comme pour les noms.
"""

from django.db import migrations
from django.db.models import F


def clear_descriptions(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(description=F("name")).update(description="")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_project_verbose_names"),
    ]

    operations = [
        migrations.RunPython(clear_descriptions, migrations.RunPython.noop),
    ]
