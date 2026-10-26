"""Messages d'erreur de l'analyse des notes (#226) : en français, sans jargon de
code, et en disant ce qui est attendu."""

import unittest

from django.test import SimpleTestCase

from note_taking.exceptions import InvalidNoteFileError, NoteParseError
from note_taking.qmd.files import check_metadata_date, split_front_matter
from note_taking.qmd.parser import parse_note


class ParserMessagesTests(SimpleTestCase):
    def assert_message(self, raw: str, message: str):
        with self.assertRaises(NoteParseError) as context:
            parse_note("2025-11-24", raw)
        self.assertEqual(str(context.exception), message)

    @unittest.expectedFailure
    def test_metadonnee_sans_deux_points(self):
        self.assert_message(
            "# P\n::: {.metadata}\npas de deux-points\n:::\nx",
            "Ligne 3 : métadonnée invalide (« pas de deux-points »), "
            "la forme attendue est « clé: valeur ».",
        )

    @unittest.expectedFailure
    def test_tags_sans_crochets(self):
        self.assert_message(
            "# P\n::: {.metadata}\ntags: a, b\n:::\nx",
            "Ligne 3 : les tags s'écrivent entre crochets, par exemple "
            "« tags: [a, b] ».",
        )

    @unittest.expectedFailure
    def test_bloc_de_metadonnees_dans_le_bloc_d_en_tete(self):
        self.assert_message(
            "---\ndate: 2025-11-24\n::: {.metadata}\ntags: [a]\n:::\n---\nx",
            "Ligne 4 : bloc de métadonnées ouvert dans le bloc d'en-tête, "
            "à fermer d'abord (ligne ---).",
        )


class FileMessagesTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_metadonnee_d_en_tete_sans_deux_points(self):
        with self.assertRaises(NoteParseError) as context:
            split_front_matter("---\ndate: 2025-11-24\npas de deux-points\n---\nx")
        self.assertEqual(
            str(context.exception),
            "Ligne 3 : métadonnée invalide (« pas de deux-points »), "
            "la forme attendue est « clé: valeur ».",
        )

    @unittest.expectedFailure
    def test_date_d_en_tete_differente_du_nom(self):
        with self.assertRaises(InvalidNoteFileError) as context:
            check_metadata_date("2025-11-24", {"date": "2025-11-25"})
        self.assertEqual(
            str(context.exception),
            "La date du bloc d'en-tête (2025-11-25) ne correspond pas "
            "au nom du fichier (2025-11-24.qmd).",
        )

    @unittest.expectedFailure
    def test_en_tete_sans_date(self):
        with self.assertRaises(InvalidNoteFileError) as context:
            check_metadata_date("2025-11-24", {})
        self.assertEqual(
            str(context.exception),
            "Le bloc d'en-tête doit indiquer la date de la note, celle du nom "
            "du fichier : « date: 2025-11-24 ».",
        )
