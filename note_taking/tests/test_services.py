"""Tests des services de note : import, mise à jour, note parts, TODO, images.

Ces tests figent le comportement actuel décrit dans le README, afin de
détecter toute régression lors de la restructuration (M3).
"""

import shutil
import tempfile
import unittest
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from note_taking.models import Note, NotePart, NotePartImage, Project
from note_taking.utils import (
    import_image,
    insert_note_in_table,
    process_note_parts,
    update_note_from_source_file,
)
from todolist.models import Todo

MEDIA_ROOT = tempfile.mkdtemp()

HEADER = "---\ndate: 2025-11-24\n---\n"


def qmd_file(name: str, content: str, encoding: str = "utf-8") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode(encoding))


def image_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"image", content_type="image/png")


def parts_summary(note: Note) -> list[tuple]:
    return [
        (part.project.name, part.subject, sorted(part.tags or []), part.content)
        for part in note.parts.order_by("pk")
    ]


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ServiceTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)


class ImportNoteTests(ServiceTestCase):
    def test_import_cree_la_note_et_ses_parts(self):
        note = insert_note_in_table(
            qmd_file("2025-11-24.qmd", HEADER + "# P\n## S\n### A\nx")
        )

        note.refresh_from_db()
        self.assertEqual(note.date, date(2025, 11, 24))
        self.assertFalse(note.is_test)
        self.assertEqual(note.raw, HEADER + "# P\n## S\n### A\nx")
        self.assertEqual(parts_summary(note), [("P", "S", ["A"], "x")])

    def test_projet_cree_automatiquement(self):
        insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# Nouveau\nx"))

        project = Project.objects.get(name="Nouveau")
        self.assertEqual(project.description, "Nouveau")

    def test_projet_existant_reutilise(self):
        existing = Project.objects.create(name="P", description="Existant")

        note = insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\nx"))

        self.assertEqual(note.parts.get().project, existing)
        self.assertEqual(Project.objects.count(), 1)

    def test_fichier_de_test(self):
        note = insert_note_in_table(qmd_file("TEST_2025-11-24.qmd", HEADER + "# P\nx"))

        self.assertTrue(note.is_test)
        self.assertEqual(note.date, "2025-11-24")

    def test_nom_de_fichier_invalide(self):
        with self.assertRaisesMessage(ValueError, "YYYY-MM-DD"):
            insert_note_in_table(qmd_file("note.qmd", HEADER + "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_date_en_tete_differente_du_nom(self):
        with self.assertRaisesMessage(ValueError, "pas cohérente"):
            insert_note_in_table(qmd_file("2025-11-25.qmd", HEADER + "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_sans_bloc_en_tete(self):
        with self.assertRaisesMessage(ValueError, "pas cohérente"):
            insert_note_in_table(qmd_file("2025-11-24.qmd", "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_date_deja_importee(self):
        insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\nx"))

        # Erreur de base de données brute : à remplacer par une erreur métier (#18).
        with self.assertRaises(IntegrityError), transaction.atomic():
            insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\ny"))
        self.assertEqual(Note.objects.count(), 1)

    def test_fichier_utf8_avec_bom(self):
        note = insert_note_in_table(
            qmd_file("2025-11-24.qmd", HEADER + "# P\nx", encoding="utf-8-sig")
        )
        self.assertEqual(parts_summary(note), [("P", None, [], "x")])

    @unittest.expectedFailure
    def test_echec_de_l_analyse_n_enregistre_pas_la_note(self):
        """Bug #45 : la note est enregistrée sans ses parts."""
        with self.assertRaises(NotePartImage.DoesNotExist):
            insert_note_in_table(
                qmd_file("2025-11-24.qmd", HEADER + "# P\n![Banc](banc.png)")
            )

        self.assertFalse(Note.objects.exists())


class UpdateNoteTests(ServiceTestCase):
    def setUp(self):
        self.note = insert_note_in_table(
            qmd_file("2025-11-24.qmd", HEADER + "# P\n### Ancien\nx")
        )

    def test_mise_a_jour_du_contenu_et_des_parts(self):
        new_raw = HEADER + "# P\n### Nouveau\ny"

        update_note_from_source_file(
            self.note.pk, qmd_file("TEST_2025-11-24.qmd", new_raw)
        )

        self.note.refresh_from_db()
        self.assertEqual(self.note.raw, new_raw)
        self.assertTrue(self.note.is_test)
        self.assertEqual(parts_summary(self.note), [("P", None, ["Nouveau"], "y")])

    def test_fichier_d_une_autre_date(self):
        other = "---\ndate: 2025-11-25\n---\n# P\ny"

        with self.assertRaisesMessage(ValueError, "pas la même"):
            update_note_from_source_file(
                self.note.pk, qmd_file("2025-11-25.qmd", other)
            )

        self.note.refresh_from_db()
        self.assertEqual(parts_summary(self.note), [("P", None, ["Ancien"], "x")])

    def test_date_en_tete_differente_du_nom(self):
        with self.assertRaisesMessage(ValueError, "pas cohérente"):
            update_note_from_source_file(
                self.note.pk, qmd_file("2025-11-24.qmd", "---\ndate: 2025-11-25\n---\n")
            )

    def test_en_tete_sans_date(self):
        with self.assertRaisesMessage(ValueError, "pas cohérente"):
            update_note_from_source_file(
                self.note.pk, qmd_file("2025-11-24.qmd", "---\nauteur: moi\n---\n")
            )

    def test_fichier_utf8_avec_bom(self):
        update_note_from_source_file(
            self.note.pk,
            qmd_file("2025-11-24.qmd", HEADER + "# P\ny", encoding="utf-8-sig"),
        )

        self.note.refresh_from_db()
        self.assertEqual(parts_summary(self.note), [("P", None, [], "y")])

    @unittest.expectedFailure
    def test_echec_de_l_analyse_conserve_la_note(self):
        """Bug #45 : le contenu est remplacé et les parts supprimées."""
        old_raw = self.note.raw

        with self.assertRaises(NotePartImage.DoesNotExist):
            update_note_from_source_file(
                self.note.pk,
                qmd_file("2025-11-24.qmd", HEADER + "# P\n![Banc](banc.png)"),
            )

        self.note.refresh_from_db()
        self.assertEqual(self.note.raw, old_raw)
        self.assertEqual(parts_summary(self.note), [("P", None, ["Ancien"], "x")])


class ProcessNotePartsTests(ServiceTestCase):
    def test_contenu_sans_bloc_en_tete(self):
        note = Note.objects.create(date="2025-11-24", raw="# P\n## S\nx")

        process_note_parts(note)

        self.assertEqual(parts_summary(note), [("P", "S", [], "x")])

    def test_date_en_tete_differente_de_la_note(self):
        note = Note.objects.create(
            date="2025-11-24", raw="---\ndate: 2025-11-25\n---\n# P\nx"
        )

        with self.assertRaisesMessage(ValueError, "ne correspond pas"):
            process_note_parts(note)

    def test_regeneration_remplace_les_parts(self):
        note = Note.objects.create(date="2025-11-24", raw="# P\n### A\nx\n### B\ny")
        process_note_parts(note)

        note.raw = "# P\n### C\nz"
        process_note_parts(note)

        self.assertEqual(parts_summary(note), [("P", None, ["C"], "z")])
        self.assertEqual(NotePart.objects.count(), 1)

    def test_contenu_vide(self):
        note = Note.objects.create(date="2025-11-24", raw=None)

        self.assertEqual(process_note_parts(note), [])

    def test_lignes_jointes_dans_le_contenu(self):
        note = Note.objects.create(date="2025-11-24", raw="# P\nx\n\ny")

        process_note_parts(note)

        self.assertEqual(note.parts.get().content, "x\n\ny")


class TodoGenerationTests(ServiceTestCase):
    def process(self, raw: str) -> Note:
        note = Note.objects.create(date="2025-11-24", raw=raw)
        process_note_parts(note)
        return note

    def test_une_todo_par_ligne(self):
        self.process("# P\n## S\n### TODO\n- Première\n- Seconde")

        todos = Todo.objects.order_by("pk")
        self.assertEqual([t.title for t in todos], ["Première", "Seconde"])
        for todo in todos:
            self.assertTrue(todo.created_from_note)
            self.assertEqual(todo.due_date, date(2025, 11, 24))
            self.assertEqual(todo.note_part_date, date(2025, 11, 24))
            self.assertEqual(todo.project.name, "P")

    def test_tags_de_la_part_et_sujet_sans_todo(self):
        self.process(
            "# P\n## S\n### TODO\n::: {.metadata}\ntags: [urgent]\n:::\n- Tâche"
        )

        todo = Todo.objects.get()
        self.assertEqual(
            sorted(todo.tags.values_list("name", flat=True)), ["S", "urgent"]
        )

    def test_pas_de_todo_sans_tag_todo(self):
        self.process("# P\n## S\n### Notes\n- Pas une tâche")

        self.assertFalse(Todo.objects.exists())

    def test_pas_de_doublon_au_retraitement(self):
        note = self.process("# P\n## S\n### TODO\n- Tâche")

        process_note_parts(note)

        self.assertEqual(Todo.objects.count(), 1)

    def test_ligne_modifiee_cree_une_nouvelle_todo(self):
        """Comportement voulu pour l'instant : l'ancienne TODO est conservée."""
        note = self.process("# P\n## S\n### TODO\n- Tâche")

        note.raw = "# P\n## S\n### TODO\n- Tâche modifiée"
        process_note_parts(note)

        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)),
            ["Tâche", "Tâche modifiée"],
        )

    @unittest.expectedFailure
    def test_ligne_vide_ne_cree_pas_de_todo(self):
        """Bug #42 : une ligne vide dans une part TODO crée une TODO sans titre."""
        self.process("# P\n## S\n### TODO\n- Première\n\n- Seconde")

        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)),
            ["Première", "Seconde"],
        )

    @unittest.expectedFailure
    def test_todo_sans_sujet(self):
        """Bug #43 : une part TODO sans sujet fait échouer le traitement."""
        with transaction.atomic():
            self.process("# P\n### TODO\n- Tâche")

        todo = Todo.objects.get()
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), [])


class ImageTests(ServiceTestCase):
    def test_import_image(self):
        image = import_image(image_file("banc.png"))

        self.assertEqual(image.original_path, "banc.png")
        self.assertTrue(image.file.name.startswith("note_images/"))

    def test_import_image_nom_deja_utilise(self):
        import_image(image_file("banc.png"))

        with self.assertRaisesMessage(ValueError, "existe déjà"):
            import_image(image_file("banc.png"))

    def test_reference_remplacee_par_identifiant(self):
        image = import_image(image_file("banc.png"))
        note = Note.objects.create(
            date="2025-11-24", raw="# P\n![Banc](dossier/banc.png)"
        )

        process_note_parts(note)

        self.assertEqual(note.parts.get().content, f"![Banc](image:{image.pk})")

    def test_image_non_importee(self):
        note = Note.objects.create(date="2025-11-24", raw="# P\n![Banc](banc.png)")

        # À remplacer par une erreur métier explicite (#18).
        with self.assertRaises(NotePartImage.DoesNotExist):
            process_note_parts(note)

    def test_rendu_avec_image(self):
        image = import_image(image_file("banc.png"))
        part = NotePart(
            project=Project(name="P"),
            content=f"![Banc](image:{image.pk})",
        )

        self.assertIn(f'src="{image.file.url}"', part.rendered_content())

    def test_rendu_image_supprimee(self):
        part = NotePart(project=Project(name="P"), content="![Banc](image:999)")

        self.assertIn("image-missing.png", part.rendered_content())
