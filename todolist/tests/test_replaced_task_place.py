"""Une tâche remplacée dans le bilan suit la nouvelle ligne : son projet et son niveau,
pas seulement le chemin de sa ligne (#382)."""

from unittest import expectedFailure

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import label, section_for
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


class ReplacedTaskPlaceTests(TestCase):
    def start(self, body: str) -> Task:
        """Une note dont la tâche « Une » est revue."""
        self.note = Note.objects.create(date="2025-11-24", body=body)
        process_passages(self.note)
        Task.objects.update(note_state=Task.NoteState.REVIEWED)
        return Task.objects.get(title="Une")

    def rewrite(self, old: str, new: str) -> None:
        """Le texte change dans l'éditeur, puis le bilan est enregistré tel que
        proposé : la tâche remplace celle de sa nouvelle ligne."""
        self.note.body = self.note.body.replace(old, new)
        self.note.save()
        process_passages(self.note)
        url = reverse("todolist:note_review", args=[self.note.date])
        context = self.client.get(url).context
        data: dict[str, object] = {}
        for formset in (context["new_formset"], context["gone_formset"]):
            forms = [formset.management_form, *formset.forms]
            for field in (field for form in forms for field in form):
                value = field.value()
                data[field.html_name] = "" if value is None else value
        self.assertEqual(data["gone-0-action"], "replace")
        self.client.post(url, data)

    def place(self, task: Task) -> tuple[str, str]:
        task.refresh_from_db()
        return str(task.project), label(task.section) if task.section else ""

    @expectedFailure
    def test_titre_renomme_dans_l_editeur(self):
        task = self.start("# P\n## Réunion\n### Préparation\n- [ ] Une")

        self.rewrite("Préparation", "Préparations")

        self.assertEqual(self.place(task), ("P", "Réunion › Préparations"))
        self.assertEqual(Task.objects.count(), 1)

    @expectedFailure
    def test_ancien_niveau_inutilise_oublie(self):
        self.start("# P\n## Préparation\n- [ ] Une")

        self.rewrite("Préparation", "Préparations")

        self.assertEqual(
            list(Section.objects.values_list("name", flat=True)), ["Préparations"]
        )

    @expectedFailure
    def test_niveau_parent_renomme(self):
        task = self.start("# P\n## Réunion\n### Préparation\n- [ ] Une")

        self.rewrite("Réunion", "Rencontre")

        self.assertEqual(self.place(task), ("P", "Rencontre › Préparation"))

    @expectedFailure
    def test_ligne_deplacee_dans_un_autre_projet(self):
        task = self.start("# P\n## A\n- [ ] Une\n# Q\n## B\nx")

        self.rewrite("- [ ] Une\n# Q\n## B\nx", "y\n# Q\n## B\n- [ ] Une")

        self.assertEqual(self.place(task), ("Q", "B"))

    @expectedFailure
    def test_ligne_sous_un_element_parent(self):
        """Le chemin de la ligne compte aussi ses éléments parents."""
        task = self.start("# P\n## A\n- Un point\n    - [ ] Une")

        self.rewrite("## A", "## B")

        self.assertEqual(self.place(task), ("P", "B"))

    @expectedFailure
    def test_titre_avec_attributs(self):
        task = self.start("# P\n## A {#a}\n- [ ] Une")

        self.rewrite("## A {#a}", "## B {#a}")

        self.assertEqual(self.place(task), ("P", "B"))

    @expectedFailure
    def test_texte_sans_projet_range(self):
        task = self.start("- [ ] Une")

        self.rewrite("- [ ] Une", "# P\n## A\n- [ ] Une")

        self.assertEqual(self.place(task), ("P", "A"))

    def test_ligne_sortie_de_son_projet(self):
        """Une tâche rangée ne redevient pas sans projet."""
        task = self.start("# P\n## A\n- [ ] Une")

        self.rewrite("# P\n## A\n- [ ] Une", "- [ ] Une\n# P\n## A\nx")

        self.assertEqual(self.place(task), ("P", "A"))

    def test_chemin_choisi_a_la_main_garde(self):
        task = self.start("# P\n## A\n- [ ] Une")
        task.section = section_for(Project.objects.get(name="P"), ["Ailleurs"])
        task.save()

        self.rewrite("## A", "## B")

        self.assertEqual(self.place(task), ("P", "Ailleurs"))

    def test_projet_choisi_a_la_main_garde(self):
        task = self.start("# P\n## A\n- [ ] Une")
        task.project, task.section = Project.objects.create(name="Q"), None
        task.save()

        self.rewrite("## A", "## B")

        self.assertEqual(self.place(task), ("Q", ""))
