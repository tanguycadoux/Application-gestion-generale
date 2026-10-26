"""Tests des services de note : import, mise à jour, note parts, TODO, images.

Ces tests figent le comportement actuel décrit dans le README, afin de
détecter toute régression lors de la restructuration (M3).
"""

import shutil
import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from django.test import TestCase, override_settings

from core.models import Project, Section
from core.sections import levels
from images.services import import_image
from images.tests.files import image_file
from note_taking.exceptions import (
    ImageNotFoundError,
    InvalidNoteFileError,
    NoteAlreadyExistsError,
    NoteParseError,
)
from note_taking.models import Note, NotePart
from note_taking.rendering import IMAGE_MISSING_PATH
from note_taking.services import (
    insert_note_in_table,
    process_note_parts,
    update_note_from_source_file,
)
from todolist.models import Todo

MEDIA_ROOT = tempfile.mkdtemp()

HEADER = "---\ndate: 2025-11-24\n---\n"


def qmd_file(name: str, content: str, encoding: str = "utf-8") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode(encoding))


def parts_summary(note: Note) -> list[tuple]:
    return [
        (
            part.project.name,
            levels(part.section) if part.section else [],
            sorted(part.tags.values_list("name", flat=True)),
            part.content,
        )
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
        self.assertEqual(note.body, "# P\n## S\n### A\nx")
        self.assertEqual(parts_summary(note), [("P", ["S", "A"], [], "x")])

    def test_projet_cree_automatiquement(self):
        """#19 : description vide plutôt que le nom du projet."""
        insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# Nouveau\nx"))

        project = Project.objects.get(name="Nouveau")
        self.assertEqual(project.description, "")

    def test_projet_existant_reutilise(self):
        existing = Project.objects.create(name="P", description="Existant")

        note = insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\nx"))

        self.assertEqual(note.parts.get().project, existing)
        self.assertEqual(Project.objects.count(), 1)

    def test_prefixe_test_refuse(self):
        """#63 : la notion de note de test n'existe plus."""
        with self.assertRaisesMessage(InvalidNoteFileError, "AAAA-MM-JJ"):
            insert_note_in_table(qmd_file("TEST_2025-11-24.qmd", HEADER + "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_nom_de_fichier_invalide(self):
        with self.assertRaisesMessage(InvalidNoteFileError, "AAAA-MM-JJ"):
            insert_note_in_table(qmd_file("note.qmd", HEADER + "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_date_en_tete_differente_du_nom(self):
        with self.assertRaisesMessage(InvalidNoteFileError, "au nom du fichier"):
            insert_note_in_table(qmd_file("2025-11-25.qmd", HEADER + "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_sans_bloc_en_tete(self):
        with self.assertRaisesMessage(InvalidNoteFileError, "date: 2025-11-24"):
            insert_note_in_table(qmd_file("2025-11-24.qmd", "# P\nx"))
        self.assertFalse(Note.objects.exists())

    def test_fichier_non_utf8(self):
        file = SimpleUploadedFile("2025-11-24.qmd", bytes([0xFF, 0xFE, 0x00]))

        with self.assertRaisesMessage(InvalidNoteFileError, "UTF-8"):
            insert_note_in_table(file)
        self.assertFalse(Note.objects.exists())

    def test_date_deja_importee(self):
        insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\nx"))

        with self.assertRaisesMessage(NoteAlreadyExistsError, "existe déjà"):
            insert_note_in_table(qmd_file("2025-11-24.qmd", HEADER + "# P\ny"))
        self.assertEqual(Note.objects.count(), 1)

    def test_fichier_utf8_avec_bom(self):
        note = insert_note_in_table(
            qmd_file("2025-11-24.qmd", HEADER + "# P\nx", encoding="utf-8-sig")
        )
        self.assertEqual(parts_summary(note), [("P", [], [], "x")])

    def test_echec_de_l_analyse_n_enregistre_pas_la_note(self):
        with self.assertRaises(ImageNotFoundError):
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
        update_note_from_source_file(
            self.note, qmd_file("2025-11-24.qmd", HEADER + "# P\n### Nouveau\ny")
        )

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "# P\n### Nouveau\ny")
        self.assertEqual(parts_summary(self.note), [("P", ["Nouveau"], [], "y")])

    def test_fichier_d_une_autre_date(self):
        other = "---\ndate: 2025-11-25\n---\n# P\ny"

        with self.assertRaisesMessage(InvalidNoteFileError, "date de la note"):
            update_note_from_source_file(self.note, qmd_file("2025-11-25.qmd", other))

        self.note.refresh_from_db()
        self.assertEqual(parts_summary(self.note), [("P", ["Ancien"], [], "x")])

    def test_date_en_tete_differente_du_nom(self):
        with self.assertRaisesMessage(InvalidNoteFileError, "au nom du fichier"):
            update_note_from_source_file(
                self.note, qmd_file("2025-11-24.qmd", "---\ndate: 2025-11-25\n---\n")
            )

    def test_en_tete_sans_date(self):
        with self.assertRaisesMessage(InvalidNoteFileError, "date: 2025-11-24"):
            update_note_from_source_file(
                self.note, qmd_file("2025-11-24.qmd", "---\nauteur: moi\n---\n")
            )

    def test_fichier_utf8_avec_bom(self):
        update_note_from_source_file(
            self.note,
            qmd_file("2025-11-24.qmd", HEADER + "# P\ny", encoding="utf-8-sig"),
        )

        self.note.refresh_from_db()
        self.assertEqual(parts_summary(self.note), [("P", [], [], "y")])

    def test_echec_de_l_analyse_conserve_la_note(self):
        old_raw = self.note.body

        with self.assertRaises(ImageNotFoundError):
            update_note_from_source_file(
                self.note,
                qmd_file("2025-11-24.qmd", HEADER + "# P\n![Banc](banc.png)"),
            )

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, old_raw)
        self.assertEqual(parts_summary(self.note), [("P", ["Ancien"], [], "x")])


class ProcessNotePartsTests(ServiceTestCase):
    def test_contenu_sans_bloc_en_tete(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n## S\nx")

        process_note_parts(note)

        self.assertEqual(parts_summary(note), [("P", ["S"], [], "x")])

    def test_date_en_tete_differente_de_la_note(self):
        note = Note.objects.create(
            date="2025-11-24", body="---\ndate: 2025-11-25\n---\n# P\nx"
        )

        with self.assertRaisesMessage(NoteParseError, "ne correspond pas"):
            process_note_parts(note)

    def test_regeneration_remplace_les_parts(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n### A\nx\n### B\ny")
        process_note_parts(note)

        note.body = "# P\n### C\nz"
        process_note_parts(note)

        self.assertEqual(parts_summary(note), [("P", ["C"], [], "z")])
        self.assertEqual(NotePart.objects.count(), 1)

    def test_analyse_interrompue_garde_les_parts_d_avant(self):
        """#221 : tout ou rien, note parts et tâches comprises."""
        note = Note.objects.create(date="2025-11-24", body="# P\n### A\nx")
        process_note_parts(note)

        note.body = "# P\n### TODO\n- Tâche\n# Q\n![a](absente.png)"
        with self.assertRaises(ImageNotFoundError):
            process_note_parts(note)

        self.assertEqual(parts_summary(note), [("P", ["A"], [], "x")])
        self.assertFalse(Todo.objects.exists())

    def test_contenu_vide(self):
        note = Note.objects.create(date="2025-11-24", body="")

        self.assertEqual(process_note_parts(note), [])

    def test_lignes_jointes_dans_le_contenu(self):
        note = Note.objects.create(date="2025-11-24", body="# P\nx\n\ny")

        process_note_parts(note)

        self.assertEqual(note.parts.get().content, "x\n\ny")


class TodoGenerationTests(ServiceTestCase):
    def process(self, raw: str) -> Note:
        note = Note.objects.create(date="2025-11-24", body=raw)
        process_note_parts(note)
        return note

    def test_meme_projet_que_la_note_part(self):
        """#19 : notes et TODO partagent le même modèle Project."""
        note = self.process("# P\n## S\n### TODO\n- Tâche")

        self.assertEqual(Todo.objects.get().project, note.parts.get().project)

    def test_une_todo_par_ligne(self):
        self.process("# P\n## S\n### TODO\n- Première\n- Seconde")

        todos = Todo.objects.order_by("pk")
        self.assertEqual([t.title for t in todos], ["Première", "Seconde"])
        for todo in todos:
            self.assertTrue(todo.created_from_note)
            self.assertIsNone(todo.due_date)
            self.assertEqual(todo.note_part_date, date(2025, 11, 24))
            self.assertEqual(todo.project.name, "P")

    def test_tags_de_la_part_sans_todo_et_sujet_a_part(self):
        """Le sujet de la note part devient le sujet de la tâche, pas un tag (#163)."""
        self.process(
            "# P\n## S\n### TODO\n::: {.metadata}\ntags: [urgent]\n:::\n- Tâche"
        )

        todo = Todo.objects.get()
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), ["urgent"])
        self.assertEqual(todo.section.name, "S")

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

        note.body = "# P\n## S\n### TODO\n- Tâche modifiée"
        process_note_parts(note)

        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)),
            ["Tâche", "Tâche modifiée"],
        )

    def test_ligne_vide_ne_cree_pas_de_todo(self):
        """Une ligne vide ou un tiret seul ne crée pas de TODO."""
        self.process("# P\n## S\n### TODO\n- Première\n\n-\n- Seconde")

        self.assertEqual(
            sorted(Todo.objects.values_list("title", flat=True)),
            ["Première", "Seconde"],
        )

    def test_todo_sans_sujet(self):
        self.process("# P\n### TODO\n- Tâche")

        todo = Todo.objects.get()
        self.assertEqual(list(todo.tags.values_list("name", flat=True)), [])


class ImageTests(ServiceTestCase):
    """Images dans les notes ; l'import lui-même est testé dans l'app images."""

    def test_reference_remplacee_par_identifiant(self):
        image = import_image(image_file("banc.png"))
        note = Note.objects.create(
            date="2025-11-24", body="# P\n![Banc](dossier/banc.png)"
        )

        process_note_parts(note)

        self.assertEqual(note.parts.get().content, f"![Banc](image:{image.pk})")

    def test_image_non_importee(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n![Banc](banc.png)")

        with self.assertRaises(ImageNotFoundError):
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

        self.assertIn(f'src="{static(IMAGE_MISSING_PATH)}"', part.rendered_content())


class DeepPathTests(ServiceTestCase):
    """Les titres `##` à `######` forment le chemin de la note part (#296)."""

    BODY = "# P\n## S\n### Notes\n#### Détail\nx"

    def test_chemin_de_la_note_part(self):
        note = Note.objects.create(date="2025-11-24", body=self.BODY)

        process_note_parts(note)

        self.assertEqual(
            parts_summary(note), [("P", ["S", "Notes", "Détail"], [], "x")]
        )

    def test_une_seule_section_par_niveau(self):
        process_note_parts(Note.objects.create(date="2025-11-24", body=self.BODY))
        process_note_parts(Note.objects.create(date="2025-11-25", body=self.BODY))

        self.assertEqual(
            sorted(Section.objects.values_list("name", flat=True)),
            ["Détail", "Notes", "S"],
        )

    def test_tache_sous_un_titre_todo_dans_un_chemin(self):
        body = "# P\n## S\n### Notes\n#### TODO\n- Tâche"
        note = Note.objects.create(date="2025-11-24", body=body)

        process_note_parts(note)

        part = note.parts.get()
        self.assertEqual(levels(part.section), ["S", "Notes"])
        self.assertEqual(list(part.tags.values_list("name", flat=True)), ["TODO"])
        self.assertEqual(part.heading_path, "P › S › Notes › TODO")
        todo = Todo.objects.get()
        self.assertEqual(levels(todo.section), ["S", "Notes"])

    def test_niveaux_inutilises_oublies_a_la_mise_a_jour(self):
        note = Note.objects.create(date="2025-11-24", body=self.BODY)
        process_note_parts(note)

        note.body = "# P\n## S\nx"
        process_note_parts(note)

        self.assertEqual(list(Section.objects.values_list("name", flat=True)), ["S"])
