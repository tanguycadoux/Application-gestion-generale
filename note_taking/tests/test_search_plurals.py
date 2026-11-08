"""Singulier et pluriel équivalents dans la recherche (#372).

Chaque mot a une forme réduite (sans casse ni accents, sans s ni x final, -aux en
-al), dans l'index comme dans la requête ; la phrase exacte et le préfixe restent tels
qu'écrits, et le surlignage marque le mot tel qu'il est écrit dans la note.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from core.models import Project, Section
from core.tables import fold
from note_taking.models import Note, NotePart
from note_taking.search import group_by_note, search_note_parts
from note_taking.search_index import search_parts, similar_terms
from note_taking.search_query import parse_query
from note_taking.word_forms import (
    TOKEN_REGEX,
    reduce_text,
    reduce_word,
    written_forms,
)


class ReduceWordTests(SimpleTestCase):
    def test_s_final_retire(self):
        self.assertEqual(reduce_word("thermiques"), "thermique")
        self.assertEqual(reduce_word("reunions"), "reunion")

    def test_x_final_retire(self):
        self.assertEqual(reduce_word("bijoux"), "bijou")
        self.assertEqual(reduce_word("cheveux"), "cheveu")
        self.assertEqual(reduce_word("tableaux"), "tableau")

    def test_aux_devient_al(self):
        self.assertEqual(reduce_word("journaux"), "journal")
        self.assertEqual(reduce_word("chevaux"), "cheval")

    def test_le_singulier_ne_change_pas(self):
        for word in ["thermique", "journal", "tableau", "reunion"]:
            with self.subTest(word=word):
                self.assertEqual(reduce_word(word), word)

    def test_mots_courts_intacts(self):
        for word in ["bus", "os", "gaz", "mots", "mais", "mois", "fois", "taux"]:
            with self.subTest(word=word):
                self.assertEqual(reduce_word(word), word)

    def test_mot_avec_chiffre_intact(self):
        self.assertEqual(reduce_word("rt17s"), "rt17s")

    def test_texte_reduit_sans_casse_ni_accents_ponctuation_gardee(self):
        self.assertEqual(
            reduce_text("Calculs THERMIQUES, l'été — journaux"),
            "calcul thermique, l'ete — journal",
        )

    def test_ecritures_d_une_forme_reduite(self):
        self.assertEqual(set(written_forms("calcul")), {"calcul", "calculs", "calculx"})
        self.assertIn("journaux", written_forms("journal"))
        self.assertEqual(written_forms("mot"), ["mot"])

    def test_chaque_mot_est_parmi_les_ecritures_de_sa_forme_reduite(self):
        for word in ["Thermiques", "journaux", "tableaux", "Réunion", "porte-fenêtres"]:
            with self.subTest(word=word):
                written = " ".join(TOKEN_REGEX.findall(fold(word)))
                self.assertIn(written, written_forms(reduce_text(word)))


class PluralSearchTests(TestCase):
    """Les données de l'issue : « Chantier Nord › Calcul thermique › Hypothèses »
    (2 notes) et « Chantier Sud › Calculs thermiques » (1 note)."""

    @classmethod
    def setUpTestData(cls):
        nord = Project.objects.create(name="Chantier Nord")
        sud = Project.objects.create(name="Chantier Sud")
        calcul = Section.objects.create(project=nord, name="Calcul thermique")
        hypotheses = Section.objects.create(
            project=nord, parent=calcul, name="Hypothèses"
        )
        calculs = Section.objects.create(project=sud, name="Calculs thermiques")
        first = Note.objects.create(date="2026-10-01")
        second = Note.objects.create(date="2026-10-02")
        nord_path = "Chantier Nord › Calcul thermique › Hypothèses"
        cls.n1 = cls.part(first, nord, hypotheses, nord_path, "Parois retenues")
        cls.n2 = cls.part(second, nord, hypotheses, nord_path, "Conductivité")
        cls.s1 = cls.part(
            second, sud, calculs, "Chantier Sud › Calculs thermiques", "Bilan"
        )
        cls.other = cls.part(first, sud, None, "Chantier Sud", "Réunions de chantier")

    @staticmethod
    def part(note, project, section, heading_path, content):
        return NotePart.objects.create(
            note=note,
            project=project,
            section=section,
            heading_path=heading_path,
            content=content,
        )

    def search(self, text):
        query = parse_query(text)
        return query, search_note_parts(query)

    def exact(self, text):
        """Sans l'élargissement aux fautes (#200) : l'index seul."""
        return search_note_parts(parse_query(text), expand=False)

    def test_le_singulier_trouve_le_pluriel(self):
        query, results = self.search("calcul thermique")

        self.assertEqual(set(results), {self.n1, self.n2, self.s1})
        self.assertEqual(query.expansions, [])

    def test_le_pluriel_trouve_le_singulier_sans_elargissement(self):
        query, results = self.search("calculs thermiques")

        self.assertEqual(set(results), {self.n1, self.n2, self.s1})
        self.assertEqual(query.expansions, [])

    def test_un_mot_courant_trouve_ses_deux_formes(self):
        _, results = self.search("thermique")

        self.assertEqual(set(results), {self.n1, self.n2, self.s1})

    def test_dans_le_texte(self):
        self.assertEqual(self.exact("réunion"), [self.other])
        self.assertEqual(self.exact("REUNIONS"), [self.other])

    def test_aux_et_eaux(self):
        note = Note.objects.create(date="2026-10-03")
        project = Project.objects.get(name="Chantier Sud")
        journaux = self.part(note, project, None, "", "Les journaux de bord")
        tableaux = self.part(note, project, None, "", "Deux tableaux")

        self.assertEqual(self.exact("journal"), [journaux])
        self.assertEqual(self.exact("tableau"), [tableaux])

    def test_la_phrase_exacte_reste_exacte(self):
        self.assertEqual(self.search('"calculs thermiques"')[1], [self.s1])
        self.assertEqual(set(self.search('"calcul thermique"')[1]), {self.n1, self.n2})

    def test_le_prefixe_marche_toujours(self):
        self.assertEqual(set(self.search("therm*")[1]), {self.n1, self.n2, self.s1})

    def test_exclure_un_mot_exclut_ses_deux_formes(self):
        self.assertEqual(self.search("chantier -thermiques")[1], [self.other])
        self.assertEqual(self.search("chantier -thermique")[1], [self.other])

    def test_les_mots_courts_ne_se_confondent_pas(self):
        note = Note.objects.create(date="2026-10-03")
        project = Project.objects.get(name="Chantier Sud")
        self.part(note, project, None, "", "mais encore un bus")

        self.assertEqual(self.search("mai")[1], [])
        self.assertEqual(search_note_parts(parse_query("bu"), expand=False), [])

    def test_chemin_singulier_trouve_le_niveau_au_pluriel(self):
        _, results = self.search('chemin:"calcul thermique"')

        self.assertEqual(set(results), {self.n1, self.n2, self.s1})

    def test_chemin_a_plusieurs_niveaux_au_singulier(self):
        _, results = self.search('chemin:"Calculs thermiques/Hypothèse"')

        self.assertEqual(set(results), {self.n1, self.n2})

    def test_exclure_un_chemin_exclut_ses_deux_formes(self):
        _, results = self.search('chantier -chemin:"calculs thermiques"')

        self.assertEqual(results, [self.other])


class PluralTypoTests(TestCase):
    """L'élargissement aux fautes (#200) compte le singulier et le pluriel ensemble."""

    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.note = Note.objects.create(date="2026-10-01")

    def part(self, content):
        return NotePart.objects.create(
            note=self.note, project=self.project, content=content
        )

    def test_le_pluriel_n_est_pas_un_mot_proche(self):
        self.part("thermiques")

        self.assertEqual(similar_terms("thermique", 2), [])

    def test_singulier_et_pluriel_comptent_ensemble(self):
        """Un mot présent dans 2 note parts, au singulier et au pluriel, n'est pas rare."""
        one = self.part("thermique")
        two = self.part("thermiques")
        self.part("thermiqua")

        query = parse_query("thermique")
        results = search_note_parts(query)

        self.assertEqual(set(results or []), {one, two})
        self.assertEqual(query.expansions, [])

    def test_faute_et_pluriel(self):
        p = self.part("la résistance thermique")

        query = parse_query("thermiqes")
        results = search_note_parts(query)

        self.assertEqual(results, [p])
        self.assertEqual(query.expansions, [("thermiqes", "thermique")])


class PluralSnippetTests(TestCase):
    """Le surlignage marque le mot tel qu'il est écrit dans la note."""

    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.note = Note.objects.create(date="2026-10-15")

    def part(self, content, heading_path=""):
        return NotePart.objects.create(
            note=self.note,
            project=self.project,
            content=content,
            heading_path=heading_path,
        )

    def snippet(self, text, part):
        query = parse_query(text)
        parts = search_note_parts(query) or []
        hits = [hit for group in group_by_note(query, parts) for hit in group.hits]
        found = [hit.snippet for hit in hits if hit.part == part]
        assert found, f"{part.content} n'est pas trouvée"
        return found[0]

    def common(self, text):
        """Deux autres note parts : le mot n'est plus rare, donc pas élargi (#200)."""
        self.part(text)
        self.part(text)

    def test_le_pluriel_du_texte_est_surligne(self):
        part = self.part("Les journaux de bord du banc")
        self.common("journal")

        snippet = self.snippet("journal", part)

        self.assertIn("<mark>journaux</mark>", snippet)

    def test_le_titre_au_pluriel_est_surligne(self):
        part = self.part("Bilan", heading_path="Chantier Sud › Calculs thermiques")
        self.common("calcul thermique")

        snippet = self.snippet("calcul thermique", part)

        self.assertIn("<mark>Calculs</mark>", snippet)
        self.assertIn("<mark>thermiques</mark>", snippet)

    def test_le_singulier_cherche_au_pluriel_est_surligne(self):
        part = self.part("Le calcul thermique du banc")

        snippet = self.snippet("calculs", part)

        self.assertIn("<mark>calcul</mark>", snippet)

    def test_mot_phrase_et_prefixe_surlignes_ensemble(self):
        part = self.part("Réglages thermiques du banc d'essai, pour la conductivité")
        self.common("thermique")

        snippet = self.snippet("""thermique "banc d'essai" conduct*""", part)

        self.assertIn("<mark>thermiques</mark>", snippet)
        self.assertIn("<mark>banc d&#x27;essai</mark>", snippet)
        self.assertIn("<mark>conductivité</mark>", snippet)

    def test_page_de_recherche(self):
        self.part("Bilan", heading_path="Chantier Sud › Calculs thermiques")
        self.common("calcul thermique")

        response = self.client.get(
            reverse("note_taking:notes_search"), {"q": "calcul thermique"}
        )

        self.assertContains(response, "<mark>Calculs</mark>")
        self.assertNotContains(response, "Recherche élargie")


class IndexPluralTests(TestCase):
    def test_l_index_trouve_le_pluriel(self):
        project = Project.objects.create(name="Alpha")
        note = Note.objects.create(date="2026-10-15")
        part = NotePart.objects.create(
            note=note, project=project, content="Mesures thermiques"
        )

        self.assertEqual(search_parts("mesure thermique"), [part.pk])


class ReducedIndexMigrationTests(TransactionTestCase):
    """La migration garde l'index existant et y ajoute les formes réduites."""

    before = [("note_taking", "0039_savedsearch")]
    after = [("note_taking", "0040_notepart_search_words")]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)

    def setUp(self):
        self.migrate(self.before)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO note_part_search(rowid, content, headings) "
                "VALUES (41, 'Les journaux de bord', 'Alpha › Calculs thermiques')"
            )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM note_part_search")

    def rows(self, sql, params=()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def test_l_index_existant_gagne_les_formes_reduites(self):
        self.migrate(self.after)

        self.assertEqual(
            self.rows(
                "SELECT rowid FROM note_part_search WHERE note_part_search MATCH %s",
                ['words : "journal" AND words : "calcul"'],
            ),
            [(41,)],
        )
        self.assertEqual(
            self.rows("SELECT content, headings FROM note_part_search"),
            [("Les journaux de bord", "Alpha › Calculs thermiques")],
        )
        vocabulary = self.rows(
            "SELECT term FROM note_part_vocab WHERE col = 'words' ORDER BY term"
        )
        self.assertIn(("journal",), vocabulary)
        self.assertNotIn(("journaux",), vocabulary)

    def test_retour_en_arriere(self):
        self.migrate(self.after)
        self.migrate(self.before)

        self.assertEqual(
            self.rows("SELECT rowid, content, headings FROM note_part_search"),
            [(41, "Les journaux de bord", "Alpha › Calculs thermiques")],
        )
        self.assertIn(("journaux",), self.rows("SELECT term FROM note_part_vocab"))
