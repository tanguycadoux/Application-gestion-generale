"""Les tâches issues des notes gardent leur fiche quand les titres répétés d'une
note sont regroupés (#315) : leur chemin ne change pas."""

from django.test import TestCase

from note_taking.models import Note
from note_taking.qmd.regroup import regroup_headings, repeated_headings
from note_taking.services import process_passages
from todolist.models import Task


class RegroupTasksTests(TestCase):
    BODY = (
        "# P\n- [ ] a\n  - [ ] a1\n\n## S\n- [ ] s1\n\n# Q\n- [ ] q\n\n"
        "# P\n- [ ] b\n\n## S\n- [ ] s2\n\n## T\n- [ ] t\n"
    )

    def setUp(self):
        self.note = Note.objects.create(date="2026-11-26", body=self.BODY)
        process_passages(self.note)

    def tasks(self) -> dict[str, tuple[int, str, str | None]]:
        return {
            task.title: (
                task.pk,
                task.section.name if task.section else "",
                task.parent.title if task.parent else None,
            )
            for task in Task.objects.select_related("section", "parent")
        }

    def test_meme_fiche_meme_chemin(self):
        before = self.tasks()
        keys = {heading.key for heading in repeated_headings(self.BODY)}
        self.note.body = regroup_headings(self.BODY, keys)
        self.note.save()

        process_passages(self.note)

        self.assertEqual(self.tasks(), before)
        self.assertEqual(Task.objects.count(), 7)
