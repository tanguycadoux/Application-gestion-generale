"""Tâches issues des notes : une sous-liste crée des sous-tâches (#238).

L'imbrication suit la règle de Pandoc, celle du rendu (#229) : une ligne est
sous une autre si son marqueur commence au moins à la colonne du texte de la
ligne parente.
"""

import unittest

from django.test import TestCase

from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class NoteSubtaskTests(TestCase):
    def save_note(self, *lines: str, date: str = "2025-11-24") -> Note:
        body = "# P\n### TODO\n" + "\n".join(lines)
        note, _ = Note.objects.update_or_create(date=date, defaults={"body": body})
        process_note_parts(note)
        return note

    def tree(self) -> dict[str, str | None]:
        """Titre de chaque tâche, et titre de sa parente."""
        return {
            todo.title: todo.parent.title if todo.parent else None
            for todo in Todo.objects.select_related("parent")
        }

    @unittest.expectedFailure
    def test_sous_liste_a_deux_espaces(self):
        self.save_note("- Parent", "  - Enfant", "- Autre")

        self.assertEqual(
            self.tree(), {"Parent": None, "Enfant": "Parent", "Autre": None}
        )

    @unittest.expectedFailure
    def test_plusieurs_niveaux(self):
        self.save_note("- A", "  - B", "    - C", "  - D", "- E")

        self.assertEqual(
            self.tree(), {"A": None, "B": "A", "C": "B", "D": "A", "E": None}
        )

    @unittest.expectedFailure
    def test_liste_numerotee_trois_espaces(self):
        self.save_note("1. A", "   - B", "2. C")

        self.assertEqual(self.tree(), {"A": None, "B": "A", "C": None})

    def test_un_espace_ne_suffit_pas(self):
        """Pandoc : un marqueur avant la colonne du texte reste au même niveau."""
        self.save_note("- A", " - B")

        self.assertEqual(self.tree(), {"A": None, "B": None})

    def test_numerotee_deux_espaces_ne_suffisent_pas(self):
        self.save_note("1. A", "  - B")

        self.assertEqual(self.tree(), {"A": None, "B": None})

    @unittest.expectedFailure
    def test_cases_a_cocher(self):
        self.save_note("- [ ] A", "  - [x] B")

        self.assertEqual(self.tree(), {"A": None, "B": "A"})

    @unittest.expectedFailure
    def test_ligne_sans_marqueur_sous_un_element(self):
        """Pandoc en fait la suite de l'élément : elle devient sa sous-tâche."""
        self.save_note("- A", "  précision")

        self.assertEqual(self.tree(), {"A": None, "précision": "A"})

    def test_parent_pose_seulement_a_la_creation(self):
        """Une tâche existante n'est pas rattachée d'office (décision du
        2026-10-26) : son parent a pu être choisi à la main."""
        self.save_note("- A", "- B")
        self.save_note("- A", "  - B")

        self.assertEqual(self.tree(), {"A": None, "B": None})

    @unittest.expectedFailure
    def test_nouvelle_ligne_sous_une_tache_existante(self):
        self.save_note("- A")
        self.save_note("- A", "  - B")

        self.assertEqual(self.tree(), {"A": None, "B": "A"})

    def test_rattachement_manuel_garde(self):
        self.save_note("- A", "  - B", "- C")
        b = Todo.objects.get(title="B")
        b.parent = Todo.objects.get(title="C")
        b.save()

        self.save_note("- A", "  - B", "- C")

        self.assertEqual(self.tree(), {"A": None, "B": "C", "C": None})

    def test_meme_texte_sous_lui_meme_sans_boucle(self):
        self.save_note("- A", "  - A")

        self.assertEqual(self.tree(), {"A": None})
