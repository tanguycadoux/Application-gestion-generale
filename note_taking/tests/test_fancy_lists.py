"""Listes ordonnées de Pandoc : lettres, chiffres romains, `#.`, exemples (#325).

Les résultats attendus sont ceux de Pandoc 3.10, le Pandoc de Quarto 1.10.19, relevés avec
`pandoc -f markdown -t html` et `quarto render` (extension `fancy_lists`).
"""

import re

from django.test import SimpleTestCase

from note_taking.qmd.lists import LIST_ITEM_REGEX, parse_marker
from note_taking.rendering import render_markdown


def marker(text: str, space: str = " ", context=None):
    return parse_marker(text, space, context)


class MarkerTests(SimpleTestCase):
    def test_puces(self):
        for text in ("-", "*", "+"):
            with self.subTest(text=text):
                self.assertEqual(marker(text).kind, "bullet")

    def test_decimaux(self):
        self.assertEqual(
            [(m.kind, m.delimiter, m.value) for m in map(marker, ("1.", "12)", "(3)"))],
            [("decimal", ".", 1), ("decimal", ")", 12), ("decimal", "()", 3)],
        )

    def test_lettres_minuscules_une_seule(self):
        for text, value in (("a.", 1), ("c.", 3), ("j.", 10), ("v.", 22), ("x.", 24)):
            with self.subTest(text=text):
                found = marker(text)
                self.assertEqual(
                    (found.kind, found.upper, found.value), ("alpha", False, value)
                )

    def test_romains_minuscules(self):
        for text, value in (
            ("i.", 1),
            ("ii.", 2),
            ("iv.", 4),
            ("xii.", 12),
            ("mix.", 1009),
        ):
            with self.subTest(text=text):
                found = marker(text)
                self.assertEqual(
                    (found.kind, found.upper, found.value), ("roman", False, value)
                )

    def test_majuscule_seule_avec_point_demande_deux_espaces(self):
        """Une initiale (« A. Dupont ») n'est pas une liste."""
        self.assertIsNone(marker("A.", " "))
        self.assertIsNone(marker("I.", " "))
        self.assertIsNone(marker("A.", ""))
        self.assertEqual(marker("A.", "  ").kind, "alpha")
        self.assertEqual(marker("I.", "  ").kind, "roman")

    def test_majuscule_avec_parenthese_un_espace_suffit(self):
        self.assertEqual(marker("A)", " ").kind, "alpha")
        self.assertEqual(marker("(A)", " ").kind, "alpha")
        self.assertEqual(marker("I)", " ").kind, "roman")

    def test_romain_majuscule_de_plusieurs_lettres_sans_deux_espaces(self):
        found = marker("II.", " ")

        self.assertEqual((found.kind, found.upper, found.value), ("roman", True, 2))

    def test_refuses(self):
        for text in (
            "aa.",
            "bb.",
            "Mr.",
            "iiii.",
            "Ii.",
            "1",
            "a",
            "(a.",
            "(#)",
            "@.",
            "ab)",
        ):
            with self.subTest(text=text):
                self.assertIsNone(marker(text, "  "))

    def test_numerotation_automatique_et_exemples(self):
        self.assertEqual(marker("#.").kind, "auto")
        self.assertEqual(marker("#)").kind, "auto")
        self.assertEqual(marker("(@)").kind, "example")
        self.assertEqual(marker("(@exemple-1)").kind, "example")

    def test_contexte_liste_de_lettres_i_reste_une_lettre(self):
        alpha = marker("a.")

        found = marker("i.", " ", alpha)

        self.assertEqual((found.kind, found.value), ("alpha", 9))

    def test_contexte_liste_de_romains_v_x_c_restent_des_romains(self):
        roman = marker("iv.")

        for text, value in (("v.", 5), ("x.", 10), ("c.", 100)):
            with self.subTest(text=text):
                found = marker(text, " ", roman)
                self.assertEqual((found.kind, found.value), ("roman", value))

    def test_contexte_sans_effet_si_le_marqueur_ne_convient_pas(self):
        roman = marker("i.")

        # « j » n'est pas un chiffre romain : c'est une lettre, donc une autre liste.
        self.assertEqual(marker("j.", " ", roman).kind, "alpha")

    def test_style_distingue_type_casse_et_delimiteur(self):
        self.assertNotEqual(marker("a.").style, marker("A.", "  ").style)
        self.assertNotEqual(marker("a.").style, marker("a)").style)
        self.assertNotEqual(marker("a.").style, marker("1.").style)
        self.assertEqual(marker("a.").style, marker("b.").style)

    def test_type_de_liste_html(self):
        self.assertEqual(
            [marker(t, "  ").list_type for t in ("1.", "a.", "A.", "i.", "I.", "#.")],
            ["1", "a", "A", "i", "I", "1"],
        )

    def test_lignes_d_elements(self):
        self.assertIsNotNone(LIST_ITEM_REGEX.match("  a. un"))
        self.assertIsNotNone(LIST_ITEM_REGEX.match("(@) un"))
        self.assertIsNone(LIST_ITEM_REGEX.match("A. Dupont"))
        self.assertIsNone(LIST_ITEM_REGEX.match("Mr. Dupont"))
        self.assertIsNone(LIST_ITEM_REGEX.match("a.un"))


OL_REGEX = re.compile(r"<ol(?P<attrs>[^>]*)>")


def lists(text: str) -> list[tuple[str, int]]:
    """(type, début) de chaque `<ol>` du rendu, dans l'ordre du document."""
    found = []
    for match in OL_REGEX.finditer(render_markdown(text)):
        attrs = match.group("attrs")
        kind = re.search(r'type="([^"]+)"', attrs)
        start = re.search(r'start="(\d+)"', attrs)
        found.append(
            (kind.group(1) if kind else "1", int(start.group(1)) if start else 1)
        )
    return found


class FancyListRenderingTests(SimpleTestCase):
    def check(self, cases: dict[str, list[tuple[str, int]]]):
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(lists(text), expected)

    def test_lettres(self):
        self.check(
            {
                "a. un\nb. deux\nc. trois": [("a", 1)],
                "a) un\nb) deux": [("a", 1)],
                "(a) un\n(b) deux": [("a", 1)],
                "A.  un\nB.  deux": [("A", 1)],
                "A) un\nB) deux": [("A", 1)],
                "(A) un\n(B) deux": [("A", 1)],
            }
        )

    def test_chiffres_romains(self):
        self.check(
            {
                "i. un\nii. deux\niii. trois": [("i", 1)],
                "i) un\nii) deux": [("i", 1)],
                "(i) un\n(ii) deux": [("i", 1)],
                "I.  un\nII.  deux": [("I", 1)],
                "II. un\nIII. deux": [("I", 2)],
            }
        )

    def test_depart_au_milieu(self):
        self.check(
            {
                "c. un\nd. deux": [("a", 3)],
                "e. un\nf. deux": [("a", 5)],
                "v. un\nw. deux": [("a", 22)],
                "ii. un\niii. deux": [("i", 2)],
                "iv. un\nv. deux": [("i", 4)],
                "5. un\n6. deux": [("1", 5)],
            }
        )

    def test_le_premier_marqueur_decide_du_type_les_suivants_suivent(self):
        self.check(
            {
                # « i » reste une lettre dans une liste de lettres.
                "a. a\nb. b\ni. c": [("a", 1)],
                # « v », « x », « c » restent des chiffres romains dans une liste de romains.
                "iv. a\nv. b\nvi. c": [("i", 4)],
                "i. a\nii. b\nx. c": [("i", 1)],
                "i. a\nii. b\nc. c": [("i", 1)],
            }
        )

    def test_un_marqueur_d_un_autre_type_ouvre_une_autre_liste(self):
        self.check(
            {
                "i. a\nj. b": [("i", 1), ("a", 10)],
                "a. a\nb. b\nii. c": [("a", 1), ("i", 2)],
                "a. a\nB.  b": [("a", 1), ("A", 2)],
                "a. a\n1. b": [("a", 1), ("1", 1)],
                "1. a\na. b": [("1", 1), ("a", 1)],
            }
        )

    def test_un_autre_separateur_ouvre_une_autre_liste(self):
        self.check(
            {"a. a\nb) b": [("a", 1), ("a", 2)], "1. a\n2) b": [("1", 1), ("1", 2)]}
        )

    def test_decimaux_avec_parenthese(self):
        self.check({"1) un\n2) deux": [("1", 1)], "(1) un\n(2) deux": [("1", 1)]})

    def test_numerotation_automatique(self):
        self.check({"#. un\n#. deux": [("1", 1)], "#) un\n#) deux": [("1", 1)]})

    def test_exemples_numerotes_dans_tout_le_document(self):
        self.check(
            {
                "(@) a\n(@) b": [("1", 1)],
                "(@x) a\n(@y) b": [("1", 1)],
                "(@) a\n(@) b\n\ntexte\n\n(@) c\n(@) d": [("1", 1), ("1", 3)],
                "(@) a\n\n1. x\n\n(@) b": [("1", 1), ("1", 1), ("1", 2)],
            }
        )

    def test_sous_listes(self):
        self.check(
            {
                "1. un\n   a. deux\n   b. trois\n2. quatre": [("1", 1), ("a", 1)],
                "a. un\n   i. deux\n   ii. trois\nb. quatre": [("a", 1), ("i", 1)],
                "1. a\n   i. b\n   ii. c": [("1", 1), ("i", 1)],
                "1. a\n   #. b\n   #. c": [("1", 1), ("1", 1)],
            }
        )

    def test_liste_lache_et_liste_interrompue(self):
        self.check(
            {
                "a. un\n\nb. deux": [("a", 1)],
                "a. un\n\ntexte\n\nb. deux": [("a", 1), ("a", 2)],
            }
        )

    def test_z_puis_deux_lettres(self):
        self.check({"z. a\naa. b": [("a", 26)]})

    def test_nombre_d_elements(self):
        html = render_markdown("iv. a\nv. b\nvi. c")

        self.assertEqual(html.count("<li>"), 3)

    def test_texte_de_l_element_conserve_sans_le_marqueur(self):
        html = render_markdown("a. un **gras**\nb. deux")

        self.assertHTMLEqual(
            html,
            '<ol type="a" class="list-lower-alpha"><li>un <strong>gras</strong></li><li>deux</li></ol>',
        )

    def test_liste_de_cases(self):
        html = render_markdown("a. [ ] tâche\nb. [x] faite")

        self.assertIn('type="a"', html)
        self.assertIn('class="list-lower-alpha"', html)
        self.assertEqual(html.count("<label>"), 2)

    def test_classe_d_affichage_selon_le_type(self):
        for text, css in (
            ("a. x", "list-lower-alpha"),
            ("A.  x", "list-upper-alpha"),
            ("i. x", "list-lower-roman"),
            ("I.  x", "list-upper-roman"),
        ):
            with self.subTest(text=text):
                self.assertIn(f'class="{css}"', render_markdown(text))

    def test_liste_numerotee_sans_type_inchangee(self):
        self.assertHTMLEqual(
            render_markdown("1. a\n2. b"), "<ol><li>a</li><li>b</li></ol>"
        )


class NotAListTests(SimpleTestCase):
    """Ce qui ressemble à un marqueur sans en être un reste du texte, comme dans Pandoc."""

    def text_of(self, text: str) -> str:
        html = render_markdown(text)
        self.assertNotIn("<ol", html)
        self.assertNotIn("<h", html)
        return re.sub(r"<[^>]+>|\s+", " ", html).strip()

    def test_initiale_avec_un_seul_espace(self):
        self.assertEqual(self.text_of("A. Dupont arrive"), "A. Dupont arrive")
        self.assertEqual(self.text_of("A. un\nB. deux"), "A. un B. deux")

    def test_romain_majuscule_seul_avec_un_espace(self):
        self.assertEqual(self.text_of("I. Introduction"), "I. Introduction")

    def test_abreviation(self):
        self.assertEqual(self.text_of("Mr. Dupont"), "Mr. Dupont")

    def test_deux_lettres_non_romaines(self):
        self.assertEqual(self.text_of("aa. un\nbb. deux"), "aa. un bb. deux")

    def test_sans_espace_apres_le_marqueur(self):
        self.assertEqual(self.text_of("a.un\nb.deux"), "a.un b.deux")

    def test_collee_a_un_paragraphe(self):
        """Une liste a besoin d'une ligne vide avant elle."""
        self.assertEqual(self.text_of("texte\na. un\nb. deux"), "texte a. un b. deux")
        self.assertEqual(self.text_of("texte\n(@) un"), "texte (@) un")

    def test_diese_point_collee_a_un_paragraphe_n_est_pas_un_titre(self):
        self.assertEqual(self.text_of("texte\n#. un"), "texte #. un")

    def test_diese_point_apres_une_puce_ouvre_une_liste_numerotee_pas_un_titre(self):
        html = render_markdown("- a\n#. suite")

        self.assertNotIn("<h", html)
        self.assertHTMLEqual(html, "<ul><li>a</li></ul><ol><li>suite</li></ol>")

    def test_marqueur_d_un_autre_type_juste_apres_un_element_ouvre_une_liste(self):
        """« b. » après « 1. a » n'est pas la suite de l'élément : une liste de lettres,
        qui commence à 2 (rang de b)."""
        self.assertEqual(lists("1. a\nb. suite"), [("1", 1), ("a", 2)])
