"""Tests des sujets et tags partagés entre notes et TODO (#20)."""

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


def process(date: str, raw: str) -> Note:
    note = Note.objects.create(date=date, body=raw)
    process_note_parts(note)
    return note


class SharedSubjectTagTests(TestCase):
    def test_sujet_partage_entre_notes(self):
        first = process("2025-11-24", "# P\n## Thermique\nx")
        second = process("2025-11-25", "# Q\n## Thermique\ny")

        self.assertEqual(first.parts.get().subject.pk, second.parts.get().subject.pk)

    def test_note_part_et_todo_partagent_les_tags(self):
        note = process(
            "2025-11-24",
            "# P\n## S\n### TODO\n::: {.metadata}\ntags: [urgent]\n:::\n- Tâche",
        )

        part_tags = set(note.parts.get().tags.all())
        todo_tags = set(Todo.objects.get().tags.all())
        self.assertEqual({tag.name for tag in part_tags & todo_tags}, {"urgent"})

    def test_sujet_inutilise_absent_de_la_recherche(self):
        note = process("2025-11-24", "# P\n## Ancien sujet\nx")
        note.body = "# P\n## Nouveau sujet\nx"
        process_note_parts(note)

        response = self.client.get(reverse("note_taking:notes_search"))

        choices = [v for v, _ in response.context["form"].fields["subjects"].choices]
        self.assertEqual(choices, ["Nouveau sujet"])
