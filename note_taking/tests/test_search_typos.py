"""Tolérance aux fautes de frappe (#200) : mots proches du vocabulaire de l'index."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.search import search_note_parts
from note_taking.search_index import edit_distance, similar_terms
from note_taking.search_query import parse_query


class EditDistanceTests(SimpleTestCase):
    def test_identiques(self):
        self.assertEqual(edit_distance("banc", "banc"), 0)

    def test_substitution_insertion_suppression(self):
        self.assertEqual(edit_distance("banc", "bane"), 1)
        self.assertEqual(edit_distance("thermiqe", "thermique"), 1)
        self.assertEqual(edit_distance("thermique", "thermiqe"), 1)

    def test_une_transposition_compte_pour_un(self):
        self.assertEqual(edit_distance("thermqiue", "thermique"), 1)

    def test_loin(self):
        self.assertEqual(edit_distance("abc", "xyz"), 3)
        self.assertEqual(edit_distance("", "abc"), 3)


class TypoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.note = Note.objects.create(date="2026-10-01")

    def part(self, content):
        return NotePart.objects.create(
            note=self.note, project=self.project, content=content
        )

    def search(self, text, **kwargs):
        query = parse_query(text)
        return query, search_note_parts(query, **kwargs)


class VocabularyTests(TypoTestCase):
    def test_mots_proches(self):
        self.part("résistance thermique du banc")

        terms = [term for term, _ in similar_terms("thermiqe", 1)]

        self.assertEqual(terms, ["thermique"])

    def test_le_mot_lui_meme_n_est_pas_propose(self):
        self.part("thermique")

        self.assertEqual(similar_terms("thermique", 2), [])

    def test_plus_proche_d_abord_puis_plus_frequent(self):
        self.part("thermique thermiques")
        self.part("thermiques")

        terms = [term for term, _ in similar_terms("thermiqe", 2)]

        self.assertEqual(terms[0], "thermique")
        self.assertIn("thermiques", terms)


class ExpansionTests(TypoTestCase):
    def test_une_faute_est_corrigee_et_affichee(self):
        p = self.part("résistance thermique du banc")

        query, results = self.search("thermiqe")

        self.assertEqual(results, [p])
        self.assertEqual(query.expansions, [("thermiqe", "thermique")])

    def test_sans_casse_ni_accents(self):
        p = self.part("résistance du banc")

        query, results = self.search("RESISTENCE")

        self.assertEqual(results, [p])
        self.assertEqual(query.expansions, [("RESISTENCE", "resistance")])

    def test_transposition(self):
        p = self.part("résistance thermique")

        query, results = self.search("thermqiue")

        self.assertEqual(results, [p])

    def test_un_mot_present_n_est_pas_elargi(self):
        self.part("thermique du banc")
        self.part("thermique encore")
        self.part("thermiques")

        query, results = self.search("thermique")

        self.assertEqual(query.expansions, [])
        self.assertEqual(len(results), 2)

    def test_un_mot_rare_est_elargi_mais_l_exact_passe_avant(self):
        faute = self.part("thermiqe")
        juste = self.part("thermique")

        query, results = self.search("thermiqe")

        self.assertEqual(results, [faute, juste])
        self.assertEqual(query.expansions, [("thermiqe", "thermique")])

    def test_les_resultats_exacts_avant_les_elargis_meme_moins_pertinents(self):
        elargi = self.part("thermique")
        exact = self.part("thermiqe " + "autre " * 40)

        _, results = self.search("thermiqe")

        self.assertEqual(results, [exact, elargi])

    def test_plusieurs_mots_dont_un_seul_fautif(self):
        p = self.part("banc thermique")
        self.part("banc seul")

        query, results = self.search("banc thermiqe")

        self.assertEqual(results, [p])
        self.assertEqual(query.expansions, [("thermiqe", "thermique")])

    def test_pas_de_mot_proche_pas_d_elargissement(self):
        self.part("thermique")

        query, results = self.search("zzzzzzzz")

        self.assertEqual(results, [])
        self.assertEqual(query.expansions, [])

    def test_seuils_de_distance(self):
        self.part("banc thermique")
        # 4 à 6 lettres : une faute ; 7 et plus : deux.
        self.assertEqual(self.search("bxxc")[1], [])  # 4 lettres, deux fautes
        self.assertEqual(len(self.search("bane")[1]), 1)
        self.assertEqual(self.search("thermiqu")[1][0].content, "banc thermique")
        self.assertEqual(len(self.search("thrmiqe")[1]), 1)  # 7 lettres, deux écarts

    def test_mots_courts_jamais_elargis(self):
        self.part("des chats")

        for text in ["dex", "ban", "ch"]:
            with self.subTest(text=text):
                query, results = self.search(text)

                self.assertEqual(query.expansions, [])
                self.assertEqual(results, [])

    def test_phrase_jamais_elargie(self):
        self.part("résistance thermique")

        query, results = self.search('"resistance thermiqe"')

        self.assertEqual(results, [])
        self.assertEqual(query.expansions, [])

    def test_prefixe_jamais_elargi(self):
        self.part("résistance thermique")

        query, results = self.search("thermiqe*")

        self.assertEqual(results, [])
        self.assertEqual(query.expansions, [])

    def test_terme_exclu_jamais_elargi(self):
        keep = self.part("banc thermique")

        query, results = self.search("banc -thermiqe")

        self.assertEqual(results, [keep])
        self.assertEqual(query.expansions, [])

    def test_valeurs_d_operateurs_jamais_elargies(self):
        self.part("thermique")

        query, results = self.search("projet:Alpah")

        self.assertEqual(results, [])
        self.assertEqual(query.expansions, [])

    def test_mot_avec_ponctuation_ou_chiffre_jamais_elargi(self):
        self.part("porte-clés rt17a")

        for text in ["porte-clef", "rt17b"]:
            with self.subTest(text=text):
                query, _ = self.search(text)

                self.assertEqual(query.expansions, [])

    def test_expand_false(self):
        self.part("thermique")
        query = parse_query("thermiqe")

        results = search_note_parts(query, expand=False)

        self.assertEqual(results, [])
        self.assertEqual(query.expansions, [])

    def test_l_index_a_jour_apres_modification(self):
        p = self.part("ancien")
        p.content = "thermique"
        p.save()

        query, results = self.search("thermiqe")

        self.assertEqual(results, [p])


class TypoPageTests(TypoTestCase):
    url = reverse("note_taking:notes_search")

    def test_l_elargissement_est_affiche_avec_son_annulation(self):
        self.part("résistance thermique")

        response = self.client.get(self.url, {"q": "thermiqe"})

        self.assertContains(response, "thermiqe")
        self.assertContains(response, "thermique")
        self.assertContains(response, "exact=1")
        self.assertContains(response, "résistance thermique")

    def test_exact_annule_l_elargissement(self):
        self.part("résistance thermique")

        response = self.client.get(self.url, {"q": "thermiqe", "exact": "1"})

        self.assertEqual(response.context["results"], [])
        self.assertNotContains(response, "exact=1")

    def test_rien_d_affiche_sans_elargissement(self):
        self.part("thermique")

        response = self.client.get(self.url, {"q": "thermique"})

        self.assertNotContains(response, "exact=1")
