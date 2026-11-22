"""Tests des chemins et tags partagés entre notes et tâches (#20, #295).

Le même nom de niveau sous deux projets est deux sections : voir
`test_sections.py`."""

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


def process(date: str, raw: str) -> Note:
    note = Note.objects.create(date=date, body=raw)
    process_passages(note)
    return note


class SharedSectionTagTests(TestCase):
    def test_niveau_partage_entre_notes_d_un_meme_projet(self):
        first = process("2025-11-24", "# P\n## Thermique\nx")
        second = process("2025-11-25", "# P\n## Thermique\ny")

        self.assertEqual(
            first.passages.get().section.pk, second.passages.get().section.pk
        )

    def test_passage_et_tache_partagent_les_tags(self):
        note = process(
            "2025-11-24",
            "# P\n## S\n::: {.metadata}\ntodo: true\n:::\n::: {.metadata}\ntags: [urgent]\n:::\n- Tâche",
        )

        part_tags = set(note.passages.get().tags.all())
        task_tags = set(Task.objects.get().tags.all())
        self.assertEqual({tag.name for tag in part_tags & task_tags}, {"urgent"})

    def test_sujet_inutilise_absent_de_la_recherche(self):
        note = process("2025-11-24", "# P\n## Ancien sujet\nx")
        note.body = "# P\n## Nouveau sujet\nx"
        process_passages(note)

        response = self.client.get(reverse("note_taking:notes_search"))

        labels = [n.label for n in response.context["path_nodes"] if n.selectable]
        self.assertEqual(labels, ["P › Nouveau sujet"])
