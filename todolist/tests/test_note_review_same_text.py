"""Bilan d'une note après un titre renommé dans l'éditeur (#382).

Une tâche dont la ligne a disparu et qui a, dans la même note, une nouvelle
tâche de même texte (casse et blancs ignorés) : « La remplacer par » cette
tâche est proposé ; « La garder » reste possible. Sous chaque tâche disparue,
l'ancien chemin, et en face le nouveau.
"""

import re

from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages
from todolist.forms import same_text_replacements
from todolist.models import Task

BEFORE = (
    "# Chantier Sud\n## Réunion de chantier\n### Préparation\n"
    "- [ ] Envoyer le plan de bornage\n"
)
AFTER = (
    "# Chantier Sud\n## Réunions de chantier\n### Préparation\n"
    "- [ ] Envoyer le plan de bornage\n"
)


def review_url() -> str:
    return reverse("todolist:note_review", args=["2025-11-24"])


class SameTextTestCase(TestCase):
    def save_note(self, body: str) -> Note:
        note, _ = Note.objects.update_or_create(
            date="2025-11-24", defaults={"body": body}
        )
        process_passages(note)
        return note

    def rename(self, before: str = BEFORE, after: str = AFTER) -> None:
        self.save_note(before)
        Task.objects.update(note_state=Task.NoteState.REVIEWED)
        self.save_note(after)

    def gone_forms(self):
        return list(self.client.get(review_url()).context["gone_formset"])


class ProposalTests(SameTextTestCase):
    def test_remplacer_propose_par_la_tache_de_meme_texte(self):
        self.rename()
        old = Task.objects.get(note_path__contains="Réunion de chantier")
        new = Task.objects.get(note_path__contains="Réunions de chantier")

        (form,) = self.gone_forms()

        self.assertEqual(form.instance, old)
        self.assertEqual(form["action"].value(), "replace")
        self.assertEqual(form["replacement"].value(), new.pk)

    def test_option_choisie_dans_la_page(self):
        self.rename()
        new = Task.objects.get(note_path__contains="Réunions de chantier")

        html = self.client.get(review_url()).content.decode()

        self.assertRegex(html, r'<option value="replace"[^>]* selected>')
        self.assertRegex(html, rf'<option value="{new.pk}"[^>]* selected>')

    def test_sans_tache_de_meme_texte_la_garder_par_defaut(self):
        self.rename(
            after=(
                "# Chantier Sud\n## Réunion de chantier\n### Préparation\n"
                "- [ ] Envoyer le plan de bornage modifié\n"
            )
        )

        (form,) = self.gone_forms()

        self.assertEqual(form["action"].value(), "keep")
        self.assertIn(form["replacement"].value(), (None, ""))

    def test_la_garder_reste_possible(self):
        self.rename()
        old = Task.objects.get(note_path__contains="Réunion de chantier")
        new = Task.objects.get(note_path__contains="Réunions de chantier")

        self.client.post(
            review_url(),
            {
                "new-TOTAL_FORMS": "1",
                "new-INITIAL_FORMS": "1",
                "new-0-id": new.pk,
                "new-0-priority": new.priority,
                "new-0-project": new.project_id,
                "new-0-section_path": "Réunions de chantier/Préparation",
                "gone-TOTAL_FORMS": "1",
                "gone-INITIAL_FORMS": "1",
                "gone-0-id": old.pk,
                "gone-0-action": "keep",
                "gone-0-replacement": new.pk,
            },
        )

        self.assertEqual(
            Task.all_objects.get(pk=old.pk).note_state, Task.NoteState.DETACHED
        )
        self.assertTrue(Task.objects.filter(pk=new.pk).exists())

    def test_tache_et_sous_tache_proposees_chacune_avec_la_sienne(self):
        self.rename(
            before=BEFORE + "  - [ ] Joindre la carte\n",
            after=AFTER + "  - [ ] Joindre la carte\n",
        )

        proposed = {
            form.instance.note_line_text: Task.objects.get(
                pk=form["replacement"].value()
            ).note_line_text
            for form in self.gone_forms()
        }

        self.assertEqual(
            proposed,
            {
                "Envoyer le plan de bornage": "Envoyer le plan de bornage",
                "Joindre la carte": "Joindre la carte",
            },
        )

    def test_une_nouvelle_tache_proposee_une_seule_fois(self):
        """Deux disparues de même texte, une seule nouvelle : la seconde n'a pas
        de proposition, le formulaire refuserait deux remplacements par la même."""
        self.rename(
            before=("# P\n## A\n- [ ] Relire\n## B\n- [ ] Relire\n"),
            after="# P\n## C\n- [ ] Relire\n",
        )

        actions = sorted(form["action"].value() for form in self.gone_forms())

        self.assertEqual(actions, ["keep", "replace"])

    def test_chemin_le_plus_proche_prefere(self):
        """Deux niveaux renommés au-dessus de deux lignes de même texte : chacune
        est proposée pour celle de même fin de chemin."""
        self.rename(
            before="# P\n## Réunion\n### A\n- [ ] Relire\n### B\n- [ ] Relire\n",
            after="# P\n## Réunions\n### A\n- [ ] Relire\n### B\n- [ ] Relire\n",
        )

        pairs = {
            form.instance.note_path: Task.objects.get(
                pk=form["replacement"].value()
            ).note_path
            for form in self.gone_forms()
        }

        self.assertEqual(
            pairs,
            {
                "P › Réunion › A": "P › Réunions › A",
                "P › Réunion › B": "P › Réunions › B",
            },
        )


class SameTextFunctionTests(TestCase):
    def test_ignore_casse_et_blancs(self):
        old = Task(pk=1, note_path="P › A", note_line_text="Relire  le Plan")
        new = Task(pk=2, note_path="P › B", note_line_text="relire le plan")

        self.assertEqual(same_text_replacements([old], [new]), {1: new})


class PathsShownTests(SameTextTestCase):
    def row(self) -> str:
        html = self.client.get(review_url()).content.decode()
        section = html[html.index('id="review-gone"') :]
        match = re.search(r'<tr class="group[^"]*">.*?</tr>', section, re.DOTALL)
        assert match is not None
        return match.group()

    def text(self, html: str) -> str:
        return " ".join(re.sub(r"<[^>]+>", " ", html).split())

    def test_ancien_et_nouveau_chemin_sous_la_tache(self):
        self.rename()

        text = self.text(self.row())

        self.assertIn(
            "Ancien chemin : Chantier Sud › Réunion de chantier › Préparation", text
        )
        self.assertIn(
            "Nouveau chemin : Chantier Sud › Réunions de chantier › Préparation", text
        )

    def test_niveau_change_mis_en_evidence(self):
        self.rename()

        row = self.row()

        self.assertRegex(row, r"<strong[^>]*>Réunion de chantier</strong>")
        self.assertRegex(row, r"<strong[^>]*>Réunions de chantier</strong>")
        self.assertNotRegex(row, r"<strong[^>]*>Chantier Sud</strong>")
        self.assertNotRegex(row, r"<strong[^>]*>Préparation</strong>")

    def test_sans_tache_de_meme_texte_seulement_l_ancien_chemin(self):
        self.rename(
            after=(
                "# Chantier Sud\n## Réunion de chantier\n### Préparation\n"
                "- [ ] Autre chose\n"
            )
        )

        text = self.text(self.row())

        self.assertIn(
            "Ancien chemin : Chantier Sud › Réunion de chantier › Préparation", text
        )
        self.assertNotIn("Nouveau chemin", text)


class PathChangesTests(TestCase):
    def test_meme_profondeur_niveau_par_niveau(self):
        from todolist.forms import path_changes

        old, new = path_changes("P › A › B › Ligne", "P › A2 › B › ligne")

        self.assertEqual(
            old, [("P", False), ("A", True), ("B", False), ("Ligne", True)]
        )
        self.assertEqual(
            new, [("P", False), ("A2", True), ("B", False), ("ligne", True)]
        )

    def test_niveau_ajoute(self):
        from todolist.forms import path_changes

        old, new = path_changes("P › B", "P › A › B")

        self.assertEqual(old, [("P", False), ("B", False)])
        self.assertEqual(new, [("P", False), ("A", True), ("B", False)])

    def test_sans_nouveau_chemin(self):
        from todolist.forms import path_changes

        self.assertEqual(path_changes("P › A", ""), ([("P", False), ("A", False)], []))
