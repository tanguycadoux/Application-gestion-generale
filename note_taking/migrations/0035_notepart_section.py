"""Le sujet d'une note part devient une section sous son projet (#295)."""

import django.db.models.deletion
from django.db import migrations, models


def subjects_to_sections(apps, schema_editor):
    """Chaque sujet utilisé devient une section de premier rang sous le projet de
    ce qui l'utilise : un même sujet sous deux projets donne deux sections. La casse
    ne distingue plus deux sections, comme les chemins (#295)."""
    Section = apps.get_model("core", "Section")
    Model = apps.get_model("note_taking", "NotePart")
    # Celles qu'une autre migration (notes, tâches) a déjà créées sont reprises.
    sections = {
        (section.project_id, section.name.casefold()): section
        for section in Section.objects.filter(parent=None)
    }
    for item in Model.objects.exclude(subject=None).select_related("subject"):
        key = (item.project_id, item.subject.name.casefold())
        if key not in sections:
            sections[key] = Section.objects.create(
                project_id=item.project_id, name=item.subject.name
            )
        Model.objects.filter(pk=item.pk).update(section=sections[key])


def sections_to_subjects(apps, schema_editor):
    """Retour en arrière : le premier niveau du chemin redevient le sujet ; les
    niveaux plus profonds, qui n'existaient pas, sont perdus."""
    Section = apps.get_model("core", "Section")
    Subject = apps.get_model("core", "Subject")
    Model = apps.get_model("note_taking", "NotePart")
    for item in Model.objects.exclude(section=None).select_related("section"):
        top = item.section
        while top.parent_id:
            top = Section.objects.get(pk=top.parent_id)
        subject, _ = Subject.objects.get_or_create(name=top.name)
        Model.objects.filter(pk=item.pk).update(subject=subject)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_section"),
        ("note_taking", "0034_notepart_heading_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="notepart",
            name="section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="note_parts",
                to="core.section",
                verbose_name="sujet",
            ),
        ),
        migrations.RunPython(subjects_to_sections, sections_to_subjects),
        migrations.RemoveField(
            model_name="notepart",
            name="subject",
        ),
    ]
