"""Tri et filtres des tableaux, dans l'URL (#178) : le module `core.tables`."""

from datetime import date

from django.contrib.staticfiles import finders
from django.http import QueryDict
from django.test import RequestFactory, SimpleTestCase

from core.tables import (
    Choice,
    ChoiceFilter,
    Column,
    DateRangeFilter,
    Filters,
    MultiChoiceFilter,
    Sort,
    Sorting,
    TextFilter,
    filter_panel,
    fold,
    header_context,
    summary_context,
)


def keep(target, value):
    return target


class SortingTests(SimpleTestCase):
    def setUp(self):
        self.sorting = Sorting(
            {
                "name": Column(key=lambda item: item["name"]),
                "year": Column(key=lambda item: item["year"], descending_first=True),
            },
            default=Sort("year", descending=True),
        )

    def test_lecture_du_parametre(self):
        self.assertEqual(self.sorting.read("name"), Sort("name", False))
        self.assertEqual(self.sorting.read("-name"), Sort("name", True))

    def test_colonne_inconnue_ou_absente_revient_au_defaut(self):
        for value in ("foo", "-foo", "", None):
            with self.subTest(value=value):
                self.assertEqual(self.sorting.read(value), Sort("year", True))

    def test_parametre_du_tri(self):
        self.assertEqual(Sort("name", True).param, "-name")
        self.assertEqual(Sort("name").param, "name")

    def test_clic_sur_la_colonne_triee_inverse_le_sens(self):
        current = Sort("name", False)

        self.assertEqual(self.sorting.next_sort(current, "name"), Sort("name", True))

    def test_clic_sur_une_autre_colonne_commence_par_son_sens_naturel(self):
        current = Sort("name", False)

        self.assertEqual(self.sorting.next_sort(current, "year"), Sort("year", True))
        self.assertEqual(
            self.sorting.next_sort(Sort("year", True), "name"), Sort("name", False)
        )

    def test_liste_python_triee_valeurs_absentes_a_la_fin_dans_les_deux_sens(self):
        items = [
            {"name": "b", "year": 2020},
            {"name": "a", "year": None},
            {"name": "c", "year": 2024},
        ]

        up = self.sorting.sort_items(items, Sort("year"))
        down = self.sorting.sort_items(items, Sort("year", True))

        self.assertEqual([i["name"] for i in up], ["b", "c", "a"])
        self.assertEqual([i["name"] for i in down], ["c", "b", "a"])

    def test_egalites_departagees_dans_le_meme_ordre_dans_les_deux_sens(self):
        items = [
            {"name": "z", "year": 2020},
            {"name": "a", "year": 2020},
            {"name": "m", "year": 2021},
        ]

        def tie(item):
            return item["name"]

        up = self.sorting.sort_items(items, Sort("year"), tie)
        down = self.sorting.sort_items(items, Sort("year", True), tie)

        self.assertEqual([i["name"] for i in up], ["a", "z", "m"])
        self.assertEqual([i["name"] for i in down], ["m", "a", "z"])


class FoldTests(SimpleTestCase):
    def test_sans_casse_ni_accents(self):
        self.assertEqual(fold("Été À Préparer"), "ete a preparer")
        self.assertEqual(fold("STRASSE"), fold("Straße"))

    def test_un_texte_sans_accent_est_inchange(self):
        self.assertEqual(fold("abc 123"), "abc 123")


class SortItemsKeyTests(SimpleTestCase):
    def test_cle_donnee_pour_des_elements_d_une_autre_forme(self):
        sorting = Sorting({"n": Column(key=lambda item: item["n"])}, default=Sort("n"))
        groups = [{"root": {"n": 3}}, {"root": {"n": 1}}, {"root": {"n": None}}]

        ordered = sorting.sort_items(
            groups, Sort("n", True), key=lambda g: g["root"]["n"]
        )

        self.assertEqual([g["root"]["n"] for g in ordered], [3, 1, None])


class MultiChoiceFilterTests(SimpleTestCase):
    def setUp(self):
        self.filter = MultiChoiceFilter(
            "project",
            "Projet",
            [Choice("A", "Alpha"), Choice("B", "Bêta"), Choice("C", "Gamma")],
            keep,
            noun="projets",
        )

    def read(self, query: str):
        return self.filter.read(QueryDict(query), [])

    def test_plusieurs_valeurs_repetees_dans_l_url(self):
        self.assertEqual(self.read("project=A&project=C"), ("A", "C"))

    def test_aucune_valeur_n_est_pas_un_filtre(self):
        self.assertIsNone(self.read(""))
        self.assertIsNone(self.read("project="))

    def test_valeurs_inconnues_ignorees_doublons_retires(self):
        self.assertEqual(self.read("project=A&project=Z&project=A"), ("A",))
        self.assertIsNone(self.read("project=Z"))

    def test_ordre_des_choix_et_non_de_l_url(self):
        self.assertEqual(self.read("project=C&project=A"), ("A", "C"))

    def test_lit_aussi_un_dictionnaire_simple(self):
        self.assertEqual(self.filter.read({"project": "B"}, []), ("B",))
        self.assertEqual(self.filter.read({"project": ["A", "B"]}, []), ("A", "B"))
        self.assertIsNone(self.filter.read({}, []))

    def test_description_un_ou_plusieurs(self):
        self.assertEqual(self.filter.describe(("B",)), "Bêta")
        self.assertEqual(self.filter.describe(("A", "C")), "2 projets")

    def test_pastille_a_cote_de_chaque_valeur(self):
        self.assertEqual(
            [c.label for c in self.filter.selected_choices(("A", "C"))],
            ["Alpha", "Gamma"],
        )


class MultiChoiceComponentTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.filters = Filters(
            {
                "projects": [
                    MultiChoiceFilter(
                        "project",
                        "Projet",
                        [Choice("A", "Alpha"), Choice("B", "Bêta")],
                        keep,
                    )
                ]
            }
        )

    def request(self, query=""):
        return self.factory.get("/notes/list/" + query)

    def test_panneau_coche_les_valeurs_choisies(self):
        request = self.request("?project=B&sort=date")
        active = self.filters.read(request.GET)

        panel = filter_panel(request, self.filters, active, "projects")

        assert panel is not None
        field = panel["fields"][0]
        self.assertEqual(field["kind"], "multichoice")
        self.assertEqual(field["selected"], ["B"])
        self.assertEqual(panel["kept"], [("sort", "date")])
        self.assertTrue(panel["active"])

    def test_panneau_sans_valeur_ne_coche_rien(self):
        request = self.request()

        panel = filter_panel(
            request, self.filters, self.filters.read(request.GET), "projects"
        )

        assert panel is not None
        self.assertEqual(panel["fields"][0]["selected"], [])
        self.assertFalse(panel["active"])

    def test_resume_une_pastille_retirable_par_valeur(self):
        request = self.request("?project=A&project=B&sort=date&page=2")
        active = self.filters.read(request.GET)

        summary = summary_context(request, self.filters, active)

        self.assertEqual(
            [item["text"] for item in summary["active"]],
            ["Projet : Alpha", "Projet : Bêta"],
        )
        first = summary["active"][0]["remove_url"]
        self.assertIn("project=B", first)
        self.assertNotIn("project=A", first)
        self.assertIn("sort=date", first)
        self.assertNotIn("page", first)

    def test_retirer_la_derniere_valeur_retire_le_parametre(self):
        request = self.request("?project=A")
        active = self.filters.read(request.GET)

        summary = summary_context(request, self.filters, active)

        self.assertEqual(summary["active"][0]["remove_url"], "/notes/list/")

    def test_retirer_tous_les_filtres(self):
        request = self.request("?project=A&project=B&sort=date")
        active = self.filters.read(request.GET)

        summary = summary_context(request, self.filters, active)

        self.assertEqual(summary["clear_url"], "?sort=date")

    def test_retirer_le_filtre_de_la_colonne(self):
        request = self.request("?project=A&project=B&sort=date")
        active = self.filters.read(request.GET)

        panel = filter_panel(request, self.filters, active, "projects")

        assert panel is not None
        self.assertEqual(panel["remove_url"], "?sort=date")


class FilterReadingTests(SimpleTestCase):
    def test_texte(self):
        text = TextFilter("title", "Titre", keep)
        errors: list[str] = []

        self.assertEqual(text.read({"title": "  réunion "}, errors), "réunion")
        self.assertIsNone(text.read({"title": "  "}, errors))
        self.assertIsNone(text.read({}, errors))

    def test_choix_refuse_une_valeur_inconnue(self):
        choice = ChoiceFilter("state", "État", [("a", "A"), ("b", "B")], keep)

        self.assertEqual(choice.read({"state": "b"}, []), "b")
        self.assertIsNone(choice.read({"state": "z"}, []))
        self.assertIsNone(choice.read({}, []))

    def test_choix_par_defaut_n_est_pas_un_filtre_actif(self):
        choice = ChoiceFilter(
            "state", "État", [("open", "En cours"), ("all", "Toutes")], keep, "open"
        )

        self.assertIsNone(choice.read({"state": "open"}, []))
        self.assertIsNone(choice.read({}, []))
        self.assertEqual(choice.read({"state": "all"}, []), "all")

    def test_choix_calcules_a_la_lecture(self):
        calls = []

        def choices():
            calls.append(1)
            return [Choice("x", "X")]

        choice = ChoiceFilter("k", "K", choices, keep)

        self.assertEqual(choice.read({"k": "x"}, []), "x")
        self.assertTrue(calls)

    def test_dates(self):
        dates = DateRangeFilter("date", "Date", keep)
        errors: list[str] = []

        self.assertEqual(
            dates.read({"date_from": "2025-11-01", "date_to": "2025-11-30"}, errors),
            (date(2025, 11, 1), date(2025, 11, 30)),
        )
        self.assertEqual(
            dates.read({"date_from": "2025-11-01"}, errors), (date(2025, 11, 1), None)
        )
        self.assertIsNone(dates.read({}, errors))
        self.assertEqual(errors, [])

    def test_dates_inversees_remises_dans_l_ordre(self):
        dates = DateRangeFilter("date", "Date", keep)

        value = dates.read({"date_from": "2025-12-01", "date_to": "2025-11-01"}, [])

        self.assertEqual(value, (date(2025, 11, 1), date(2025, 12, 1)))

    def test_date_mal_ecrite_signalee_sans_bloquer_l_autre(self):
        dates = DateRangeFilter("date", "Date", keep)
        errors: list[str] = []

        value = dates.read({"date_from": "demain", "date_to": "2025-11-30"}, errors)

        self.assertEqual(value, (None, date(2025, 11, 30)))
        self.assertEqual(len(errors), 1)
        self.assertIn("demain", errors[0])

    def test_descriptions(self):
        dates = DateRangeFilter("date", "Date", keep)
        text = TextFilter("t", "Titre", keep)
        choice = ChoiceFilter("c", "C", [("a", "Avec A")], keep)

        self.assertEqual(text.describe("x"), "contient « x »")
        self.assertEqual(choice.describe("a"), "Avec A")
        self.assertEqual(
            dates.describe((date(2025, 11, 1), None)), "depuis le 2025-11-01"
        )
        self.assertEqual(
            dates.describe((None, date(2025, 11, 1))), "jusqu'au 2025-11-01"
        )
        self.assertEqual(
            dates.describe((date(2025, 11, 1), date(2025, 11, 1))), "2025-11-01"
        )


class FiltersTests(SimpleTestCase):
    def setUp(self):
        self.filters = Filters(
            {
                "title": [
                    TextFilter(
                        "title", "Titre", lambda items, v: [i for i in items if v in i]
                    ),
                    ChoiceFilter(
                        "kind",
                        "Genre",
                        [("x", "X")],
                        lambda items, v: [i for i in items if "x" in i],
                    ),
                ],
                "date": [DateRangeFilter("date", "Date", keep)],
            }
        )

    def test_une_colonne_peut_porter_plusieurs_filtres(self):
        self.assertEqual(len(self.filters.columns["title"]), 2)
        self.assertEqual([f.key for f in self.filters.all], ["title", "kind", "date"])

    def test_lecture_des_filtres_actifs(self):
        active = self.filters.read({"title": "ab", "kind": "x", "date_from": "oups"})

        self.assertEqual(active.values, {"title": "ab", "kind": "x"})
        self.assertEqual(len(active.errors), 1)
        self.assertTrue(active)

    def test_sans_filtre_actif(self):
        self.assertFalse(self.filters.read({}))

    def test_application_enchainee(self):
        active = self.filters.read({"title": "a", "kind": "x"})

        self.assertEqual(self.filters.apply(["ax", "ay", "bx", "a"], active), ["ax"])


class ComponentContextTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.sorting = Sorting(
            {"date": Column(key=lambda x: x, descending_first=True)},
            default=Sort("date", True),
        )
        self.filters = Filters(
            {
                "date": [DateRangeFilter("date", "Date", keep)],
                "project": [
                    ChoiceFilter("project", "Projet", [("A", "A"), ("B", "B")], keep)
                ],
            }
        )

    def request(self, query=""):
        return self.factory.get("/notes/list/" + query)

    def test_en_tete_trie_inverse_le_sens_et_garde_les_filtres(self):
        request = self.request("?project=A&page=3")
        sort = Sort("date", True)

        header = header_context(
            request,
            "Date",
            "date",
            self.sorting,
            sort,
            self.filters,
            self.filters.read({}),
        )

        self.assertEqual(header["aria_sort"], "descending")
        self.assertEqual(header["arrow"], "arrow_downward")
        self.assertIn("sort=date", header["url"])
        self.assertIn("project=A", header["url"])
        self.assertNotIn("page", header["url"])

    def test_en_tete_sans_tri_ni_filtre_reste_simple(self):
        header = header_context(
            self.request(), "Autre", "autre", self.sorting, Sort("date"), None, None
        )

        self.assertEqual(header["url"], "")
        self.assertIsNone(header["filter"])

    def test_en_tete_d_une_colonne_non_triee_n_a_pas_de_fleche(self):
        sorting = Sorting(
            {"a": Column(key=lambda x: x), "date": Column(key=lambda x: x)},
            default=Sort("a"),
        )

        header = header_context(
            self.request(), "Date", "date", sorting, Sort("a"), None, None
        )

        self.assertEqual(header["arrow"], "")
        self.assertEqual(header["aria_sort"], "")
        self.assertIn("sort=date", header["url"])

    def test_panneau_reprend_le_tri_et_les_autres_filtres_en_champs_caches(self):
        request = self.request("?sort=-date&project=A&date_from=2025-11-01&page=2")
        active = self.filters.read(request.GET)

        panel = filter_panel(request, self.filters, active, "date")

        assert panel is not None
        self.assertEqual(sorted(panel["kept"]), [("project", "A"), ("sort", "-date")])
        self.assertTrue(panel["active"])
        self.assertEqual(panel["fields"][0]["values"], ["2025-11-01", ""])
        self.assertNotIn("date_from", panel["remove_url"])
        self.assertIn("project=A", panel["remove_url"])

    def test_panneau_d_un_choix_court(self):
        request = self.request("?project=B")
        active = self.filters.read(request.GET)

        panel = filter_panel(request, self.filters, active, "project")

        assert panel is not None
        field = panel["fields"][0]
        self.assertEqual(field["selected"], "B")
        self.assertFalse(field["many"])
        self.assertEqual([c.value for c in field["choices"]], ["A", "B"])

    def test_panneau_d_un_long_choix_est_une_liste_deroulante(self):
        many = Filters(
            {"c": [ChoiceFilter("c", "C", [(str(i), str(i)) for i in range(10)], keep)]}
        )

        panel = filter_panel(self.request(), many, None, "c")

        assert panel is not None
        self.assertTrue(panel["fields"][0]["many"])

    def test_des_projets_restent_des_boutons_radio_pour_garder_leur_pastille(self):
        project = type("Project", (), {"name": "P", "color": "teal"})()
        projects = Filters(
            {
                "p": [
                    ChoiceFilter(
                        "p",
                        "P",
                        [Choice(str(i), str(i), project) for i in range(10)],
                        keep,
                    )
                ]
            }
        )

        panel = filter_panel(self.request(), projects, None, "p")

        assert panel is not None
        self.assertFalse(panel["fields"][0]["many"])

    def test_le_curseur_va_dans_le_premier_champ_de_saisie(self):
        filters = Filters(
            {
                "c": [
                    ChoiceFilter("state", "État", [("a", "A"), ("b", "B")], keep),
                    TextFilter("title", "Titre", keep),
                    MultiChoiceFilter("project", "Projet", [("A", "A")], keep),
                ]
            }
        )

        panel = filter_panel(self.request(), filters, None, "c")

        assert panel is not None
        # Les boutons radio n'ont pas de curseur ; un seul champ prend le focus.
        self.assertEqual(
            [f["autofocus"] for f in panel["fields"]], [False, True, False]
        )

    def test_le_curseur_va_dans_la_recherche_d_un_filtre_a_choix_multiples(self):
        filters = Filters(
            {"c": [MultiChoiceFilter("project", "Projet", [("A", "A")], keep)]}
        )

        panel = filter_panel(self.request(), filters, None, "c")

        assert panel is not None
        self.assertTrue(panel["fields"][0]["autofocus"])

    def test_colonne_sans_filtre(self):
        self.assertIsNone(filter_panel(self.request(), self.filters, None, "autre"))
        self.assertIsNone(filter_panel(self.request(), None, None, "date"))

    def test_resume_des_filtres_actifs(self):
        request = self.request("?project=A&date_from=2025-11-01&sort=date")
        active = self.filters.read(request.GET)

        summary = summary_context(request, self.filters, active)

        texts = [item["text"] for item in summary["active"]]
        self.assertEqual(texts, ["Date : depuis le 2025-11-01", "Projet : A"])
        removal = summary["active"][1]["remove_url"]
        self.assertNotIn("project", removal)
        self.assertIn("date_from=2025-11-01", removal)
        self.assertEqual(summary["clear_url"], "?sort=date")

    def test_resume_garde_les_erreurs_sans_filtre_actif(self):
        request = self.request("?date_from=oups")
        active = self.filters.read(request.GET)

        summary = summary_context(request, self.filters, active)

        self.assertEqual(summary["active"], [])
        self.assertEqual(len(summary["errors"]), 1)

    def test_resume_vide_sans_filtres(self):
        self.assertEqual(
            summary_context(self.request(), None, None), {"active": [], "errors": []}
        )


class ChoiceSearchScriptTests(SimpleTestCase):
    def script(self) -> str:
        path = finders.find("core/table_filters.js")
        assert isinstance(path, str)
        with open(path, encoding="utf-8") as file:
            return file.read()

    def test_casse_et_accents_ignores(self):
        js = self.script()

        self.assertIn('normalize("NFD")', js)
        self.assertIn("toLowerCase()", js)

    def test_une_case_cochee_n_est_jamais_masquee(self):
        js = self.script()

        self.assertIn("!matches && !checked", js)

    def test_message_quand_rien_ne_correspond(self):
        self.assertIn("data-choice-empty", self.script())

    def test_le_champ_n_est_montre_qu_avec_le_script(self):
        self.assertIn("box.hidden = false", self.script())
