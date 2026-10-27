"""Tâches issues des notes : les cases à cocher (#297).

Une case vide `- [ ] texte` est une tâche, où qu'elle soit ; une case cochée est
ignorée. Dans une branche `todo: true`, chaque élément de liste est une tâche.
"""

from django.test import TestCase

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

BLOCK = "::: {.metadata}\ntodo: true\n:::\n"


class CheckboxTestCase(TestCase):
    def save_note(self, body: str, date: str = "2025-11-24") -> Note:
        note, _ = Note.objects.update_or_create(date=date, defaults={"body": body})
        process_note_parts(note)
        return note

    def titles(self) -> list[str]:
        return list(Todo.objects.order_by("pk").values_list("title", flat=True))

    def tree(self) -> dict[str, str | None]:
        return {
            todo.title: todo.parent.title if todo.parent else None
            for todo in Todo.objects.select_related("parent")
        }


class OpenBoxTests(CheckboxTestCase):
    def test_case_vide_est_une_tache(self):
        self.save_note("# P\n## S\n- [ ] À faire")

        self.assertEqual(self.titles(), ["À faire"])
        self.assertEqual(Todo.objects.get().section.name, "S")

    def test_element_sans_case_n_est_pas_une_tache(self):
        self.save_note("# P\n- Une idée\n- [ ] À faire")

        self.assertEqual(self.titles(), ["À faire"])

    def test_case_cochee_ignoree(self):
        self.save_note("# P\n- [x] Fait\n- [X] Fait aussi\n- [ ] À faire")

        self.assertEqual(self.titles(), ["À faire"])

    def test_listes_numerotees(self):
        self.save_note("# P\n1. [ ] Un\n2) [ ] Deux")

        self.assertEqual(self.titles(), ["Un", "Deux"])

    def test_case_dans_un_bloc_de_code_ignoree(self):
        self.save_note("# P\n```\n- [ ] Exemple\n```\n- [ ] Vraie")

        self.assertEqual(self.titles(), ["Vraie"])

    def test_fins_de_ligne_windows(self):
        self.save_note("# P\r\n- [ ] A\r\n- [ ] B\r\n")

        self.assertEqual(self.titles(), ["A", "B"])

    def test_tache_sans_tag_todo(self):
        self.save_note("# P\n- [ ] A")

        part_tags = list(Note.objects.get().parts.get().tags.all())
        self.assertEqual(part_tags, [])
        self.assertFalse(Todo.objects.get().tags.exists())


class NestingTests(CheckboxTestCase):
    def test_sous_tache_d_une_case(self):
        self.save_note("# P\n- [ ] A\n  - [ ] B")

        self.assertEqual(self.tree(), {"A": None, "B": "A"})

    def test_case_sous_un_element_simple(self):
        """« Réunion » n'est pas une tâche : sa case n'a pas de parente, mais son
        texte entre dans le chemin de la ligne (#240)."""
        self.save_note("# P\n- Réunion\n  - [ ] A")

        self.assertEqual(self.tree(), {"A": None})
        self.assertEqual(Todo.objects.get().note_path, "P › Réunion")

    def test_case_sous_une_case_cochee(self):
        self.save_note("# P\n- [x] Fait\n  - [ ] Reste")

        self.assertEqual(self.tree(), {"Reste": None})

    def test_parente_la_plus_proche_qui_est_une_tache(self):
        self.save_note("# P\n- [ ] A\n  - Détail\n    - [ ] B")

        self.assertEqual(self.tree(), {"A": None, "B": "A"})


class TodoBranchTests(CheckboxTestCase):
    def test_chaque_element_est_une_tache(self):
        self.save_note("# P\n## S\n" + BLOCK + "- A\n- B")

        self.assertEqual(self.titles(), ["A", "B"])

    def test_case_cochee_ignoree_aussi(self):
        self.save_note("# P\n" + BLOCK + "- A\n- [x] Fait")

        self.assertEqual(self.titles(), ["A"])

    def test_ligne_sans_marqueur_ignoree(self):
        self.save_note("# P\n" + BLOCK + "Un paragraphe.\n- A")

        self.assertEqual(self.titles(), ["A"])

    def test_sous_niveaux_herites(self):
        self.save_note("# P\n## S\n" + BLOCK + "### Détail\n- A")

        self.assertEqual(self.titles(), ["A"])
        self.assertEqual(Todo.objects.get().note_path, "P › S › Détail")

    def test_niveau_suivant_hors_de_la_branche(self):
        self.save_note("# P\n## S1\n" + BLOCK + "- A\n## S2\n- B")

        self.assertEqual(self.titles(), ["A"])

    def test_tags_des_taches_sans_todo(self):
        self.save_note("# P\n::: {.metadata}\ntags: [urgent]\ntodo: true\n:::\n- A")

        self.assertEqual(
            list(Todo.objects.get().tags.values_list("name", flat=True)), ["urgent"]
        )


class IdentityTests(CheckboxTestCase):
    """Passer une liste en cases garde les tâches : l'identité (#240) ne change pas."""

    def test_liste_d_une_branche_todo_puis_cases(self):
        self.save_note("# P\n## S\n" + BLOCK + "- A\n  - B")
        before = list(Todo.objects.order_by("pk").values_list("pk", flat=True))

        self.save_note("# P\n## S\n- [ ] A\n  - [ ] B")

        self.assertEqual(
            list(Todo.objects.order_by("pk").values_list("pk", flat=True)), before
        )
        self.assertEqual(
            set(Todo.objects.values_list("note_state", flat=True)),
            {Todo.NoteState.TO_REVIEW},
        )

    def test_conversion_ne_marque_rien_a_revoir_en_plus(self):
        """Les tâches d'avant ne perdent pas leur ligne."""
        note = self.save_note("# P\n## S\n" + BLOCK + "- A\n- B")
        Todo.objects.update(note_state=Todo.NoteState.REVIEWED)

        self.save_note("# P\n## S\n- [ ] A\n- [ ] B", date=str(note.date))

        self.assertEqual(
            set(Todo.objects.values_list("note_state", flat=True)),
            {Todo.NoteState.REVIEWED},
        )
        self.assertEqual(Todo.objects.count(), 2)


class FancyListTests(CheckboxTestCase):
    """Les cases des listes de lettres, de chiffres romains, `#.` et `(@)` (#325)."""

    def test_case_dans_une_liste_de_lettres(self):
        self.save_note("# P\na. [ ] A\nb. [x] B\nc. [ ] C")

        self.assertEqual(self.titles(), ["A", "C"])

    def test_sous_taches_dans_une_sous_liste_de_chiffres_romains(self):
        self.save_note("# P\n1. [ ] A\n   i. [ ] B\n   ii. [ ] C")

        self.assertEqual(self.tree(), {"A": None, "B": "A", "C": "A"})

    def test_parentheses_exemples_et_numerotation_automatique(self):
        self.save_note("# P\n(a) [ ] A\n(b) [ ] B\n\n(@) [ ] C\n\n#. [ ] D")

        self.assertEqual(self.titles(), ["A", "B", "C", "D"])

    def test_titre_sans_le_marqueur_ni_la_case(self):
        self.save_note("# P\nii) [ ] Relire")

        self.assertEqual(self.titles(), ["Relire"])

    def test_initiale_n_est_pas_un_element_de_liste(self):
        self.save_note("# P\nA. [ ] pas une tâche")

        self.assertEqual(self.titles(), [])

    def test_sans_case_hors_branche_todo_pas_de_tache(self):
        self.save_note("# P\na. Une idée")

        self.assertEqual(self.titles(), [])
