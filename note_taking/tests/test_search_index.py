"""Index plein texte des note parts (#198) : FTS5, dérivé des note parts."""

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.search_index import (
    indexed_text,
    match_expression,
    rebuild_index,
    search_parts,
)
from note_taking.services import process_note_parts


def make_part(note, content, project, heading_path=""):
    return NotePart.objects.create(
        note=note, project=project, content=content, heading_path=heading_path
    )


def indexed_rows() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM note_part_search")
        return cursor.fetchone()[0]


class IndexedTextTests(TestCase):
    def test_le_texte_est_gardé(self):
        self.assertEqual(indexed_text("Un **mot** utile"), "Un **mot** utile")

    def test_bloc_de_métadonnées_retiré(self):
        content = "avant\n::: {.metadata}\ntags: urgent\n:::\naprès"

        self.assertEqual(indexed_text(content), "avant\naprès")

    def test_référence_d_image_retirée_légende_gardée(self):
        content = "Voir ![Schéma du banc](image:12){width=50%} ici"

        text = indexed_text(content)

        self.assertIn("Schéma du banc", text)
        self.assertNotIn("image:12", text)


class MatchExpressionTests(TestCase):
    def test_chaque_mot_est_une_phrase_entre_guillemets(self):
        self.assertEqual(match_expression("bonjour monde"), '"bonjour" "monde"')

    def test_un_guillemet_est_doublé(self):
        self.assertEqual(match_expression('a"b'), '"a""b"')

    def test_texte_vide(self):
        self.assertIsNone(match_expression("   "))
        self.assertIsNone(match_expression(""))

    def test_opérateurs_fts_neutralisés(self):
        # NEAR, OR, * et : ne sont pas interprétés par FTS5.
        self.assertEqual(match_expression("a OR b:c"), '"a" "OR" "b:c"')


class IndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.note = Note.objects.create(date="2025-11-24")
        cls.autre = Note.objects.create(date="2025-11-25")

    def test_une_note_part_créée_est_cherchable(self):
        part = make_part(self.note, "Mesure de la résistance thermique", self.project)

        self.assertEqual(search_parts("thermique"), [part.pk])

    def test_insensible_à_la_casse_et_aux_accents(self):
        part = make_part(self.note, "Résistance THERMIQUE", self.project)

        self.assertEqual(search_parts("resistance thermique"), [part.pk])
        self.assertEqual(search_parts("RÉSISTANCE"), [part.pk])

    def test_les_titres_sont_indexés(self):
        part = make_part(
            self.note, "x", self.project, heading_path="Alpha › Calibration"
        )

        self.assertEqual(search_parts("calibration"), [part.pk])

    def test_tous_les_mots_sont_requis(self):
        make_part(self.note, "alpha seul", self.project)
        both = make_part(self.note, "alpha et beta", self.project)

        self.assertEqual(search_parts("alpha beta"), [both.pk])

    def test_aucun_résultat(self):
        make_part(self.note, "du texte", self.project)

        self.assertEqual(search_parts("absent"), [])

    def test_texte_vide_ne_cherche_rien(self):
        make_part(self.note, "du texte", self.project)

        self.assertEqual(search_parts(""), [])

    def test_la_syntaxe_fts_ne_plante_pas(self):
        make_part(self.note, "du texte", self.project)

        for text in ['"', "a*", "NEAR(", "(", "a AND", "col:x", "-x", "^"]:
            with self.subTest(text=text):
                search_parts(text)

    def test_les_métadonnées_ne_sont_pas_cherchables(self):
        make_part(self.note, "::: {.metadata}\ntags: urgent\n:::\ncorps", self.project)

        self.assertEqual(search_parts("urgent"), [])

    def test_le_plus_pertinent_vient_en_premier(self):
        faible = make_part(self.note, "thermique " + "autre " * 40, self.project)
        fort = make_part(self.note, "thermique", self.project)

        self.assertEqual(search_parts("thermique"), [fort.pk, faible.pk])

    def test_modifier_une_note_part_met_l_index_à_jour(self):
        part = make_part(self.note, "ancien", self.project)

        part.content = "nouveau"
        part.save()

        self.assertEqual(search_parts("ancien"), [])
        self.assertEqual(search_parts("nouveau"), [part.pk])

    def test_supprimer_une_note_part_la_retire_de_l_index(self):
        part = make_part(self.note, "texte", self.project)

        part.delete()

        self.assertEqual(search_parts("texte"), [])
        self.assertEqual(indexed_rows(), 0)

    def test_supprimer_une_note_retire_ses_note_parts(self):
        make_part(self.note, "texte", self.project)
        kept = make_part(self.autre, "texte", self.project)

        self.note.delete()

        self.assertEqual(search_parts("texte"), [kept.pk])

    def test_recalculer_les_note_parts_reconstruit_l_index(self):
        self.note.body = "# Alpha\n\nbanc d'essai\n"
        self.note.save()
        process_note_parts(self.note)

        first = search_parts("essai")
        process_note_parts(self.note)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(search_parts("essai")), 1)
        self.assertEqual(indexed_rows(), NotePart.objects.count())

    def test_rebuild_index_repart_des_note_parts(self):
        part = make_part(self.note, "texte", self.project)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM note_part_search")
            cursor.execute(
                "INSERT INTO note_part_search(rowid, content, headings) "
                "VALUES (999999, 'fantôme', '')"
            )

        rebuild_index()

        self.assertEqual(search_parts("texte"), [part.pk])
        self.assertEqual(search_parts("fantôme"), [])
        self.assertEqual(indexed_rows(), 1)


class ReprocessNotesIndexTests(TestCase):
    def test_reprocess_notes_reconstruit_l_index(self):
        note = Note.objects.create(date="2025-11-24", body="# Alpha\n\nbanc\n")
        process_note_parts(note)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM note_part_search")

        call_command("reprocess_notes", stdout=StringIO())

        self.assertEqual(len(search_parts("banc")), 1)
