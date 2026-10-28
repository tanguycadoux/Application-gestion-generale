"""Analyseur de la requête de recherche (#199) : sans accès à la base."""

from datetime import date

from django.test import SimpleTestCase

from note_taking.search_query import Term, parse_query


def texts(query) -> list[tuple[str, str, bool]]:
    return [(t.text, t.kind, t.negated) for t in query.terms]


class FreeTextTests(SimpleTestCase):
    def test_requete_vide(self):
        for text in ["", "   ", None]:
            with self.subTest(text=text):
                query = parse_query(text)

                self.assertFalse(query)
                self.assertEqual(query.errors, [])

    def test_mots_libres(self):
        query = parse_query("banc  thermique")

        self.assertEqual(
            texts(query), [("banc", "word", False), ("thermique", "word", False)]
        )

    def test_phrase_exacte(self):
        query = parse_query('"résistance thermique" banc')

        self.assertEqual(
            texts(query),
            [("résistance thermique", "phrase", False), ("banc", "word", False)],
        )

    def test_prefixe(self):
        self.assertEqual(texts(parse_query("therm*")), [("therm", "prefix", False)])

    def test_etoile_seule_est_ignoree(self):
        self.assertFalse(parse_query("*"))

    def test_exclusion(self):
        query = parse_query('banc -brouillon -"mauvaise piste"')

        self.assertEqual(
            texts(query),
            [
                ("banc", "word", False),
                ("brouillon", "word", True),
                ("mauvaise piste", "phrase", True),
            ],
        )

    def test_tiret_seul_ou_dans_un_mot_est_du_texte(self):
        query = parse_query("- porte-clés")

        self.assertEqual(texts(query), [("porte-clés", "word", False)])

    def test_apostrophe_n_ouvre_pas_de_guillemet(self):
        query = parse_query("l'été d'avant")

        self.assertEqual(
            texts(query), [("l'été", "word", False), ("d'avant", "word", False)]
        )

    def test_operateur_inconnu_reste_du_texte(self):
        query = parse_query("Re:thinking")

        self.assertEqual(texts(query), [("Re:thinking", "word", False)])
        self.assertEqual(query.errors, [])

    def test_ponctuation_seule_ignoree(self):
        self.assertFalse(parse_query(", ; ."))


class OperatorTests(SimpleTestCase):
    def test_projet_tag_chemin(self):
        query = parse_query("projet:Alpha tag:urgent chemin:Réunion/Préparation")

        self.assertEqual(query.projects, ["Alpha"])
        self.assertEqual(query.tags, ["urgent"])
        self.assertEqual(query.paths, ["Réunion/Préparation"])
        self.assertEqual(query.terms, [])

    def test_valeur_entre_guillemets(self):
        query = parse_query('projet:"Mon projet" chemin:"Notes / Détail"')

        self.assertEqual(query.projects, ["Mon projet"])
        self.assertEqual(query.paths, ["Notes / Détail"])

    def test_nom_d_operateur_sans_casse_ni_accents(self):
        query = parse_query("PROJET:A Chemin:B TAG:c")

        self.assertEqual(
            (query.projects, query.paths, query.tags), (["A"], ["B"], ["c"])
        )

    def test_exclusion_d_un_filtre(self):
        query = parse_query("tag:urgent -projet:Perso -tag:fini -chemin:Divers")

        self.assertEqual(query.tags, ["urgent"])
        self.assertEqual(query.not_projects, ["Perso"])
        self.assertEqual(query.not_tags, ["fini"])
        self.assertEqual(query.not_paths, ["Divers"])

    def test_operateur_sans_valeur_ignore(self):
        query = parse_query('projet: tag:"" banc')

        self.assertEqual(query.projects, [])
        self.assertEqual(query.tags, [])
        self.assertEqual(texts(query), [("banc", "word", False)])
        self.assertEqual(query.errors, [])

    def test_operateur_repete(self):
        query = parse_query("projet:A projet:B")

        self.assertEqual(query.projects, ["A", "B"])

    def test_filtre_seul_est_une_requete(self):
        self.assertTrue(parse_query("tag:urgent"))
        self.assertTrue(parse_query("-tag:urgent"))


class DateTests(SimpleTestCase):
    def dates(self, text):
        query = parse_query(text)
        return query.date_from, query.date_to

    def test_un_mois(self):
        self.assertEqual(
            self.dates("date:2026-10"), (date(2026, 10, 1), date(2026, 10, 31))
        )

    def test_une_annee(self):
        self.assertEqual(
            self.dates("date:2026"), (date(2026, 1, 1), date(2026, 12, 31))
        )

    def test_un_jour(self):
        self.assertEqual(
            self.dates("date:2026-10-15"), (date(2026, 10, 15), date(2026, 10, 15))
        )

    def test_fevrier_bissextile(self):
        self.assertEqual(self.dates("date:2024-02")[1], date(2024, 2, 29))
        self.assertEqual(self.dates("date:2026-02")[1], date(2026, 2, 28))

    def test_plage_de_mois_inclut_le_dernier_mois(self):
        self.assertEqual(
            self.dates("date:2026-09..2026-10"), (date(2026, 9, 1), date(2026, 10, 31))
        )

    def test_borne_basse_ouverte(self):
        self.assertEqual(self.dates("date:2026-09-15.."), (date(2026, 9, 15), None))

    def test_borne_haute_ouverte(self):
        self.assertEqual(self.dates("date:..2026"), (None, date(2026, 12, 31)))

    def test_bornes_inversees_remises_dans_l_ordre(self):
        self.assertEqual(
            self.dates("date:2026-10..2026-09"), (date(2026, 9, 1), date(2026, 10, 31))
        )

    def test_deux_dates_se_recoupent(self):
        self.assertEqual(
            self.dates("date:2026 date:2026-03.."),
            (date(2026, 3, 1), date(2026, 12, 31)),
        )

    def test_date_mal_ecrite_signalee_et_cherchee_telle_quelle(self):
        for value in ["2026-13", "demain", "..", "2026-02-30", "2026-1", "2026...2027"]:
            with self.subTest(value=value):
                query = parse_query(f"date:{value}")

                self.assertEqual((query.date_from, query.date_to), (None, None))
                self.assertEqual(len(query.errors), 1)
                self.assertIn(f"date:{value}", query.errors[0])
                self.assertEqual([t.text for t in query.terms], [f"date:{value}"])

    def test_exclure_une_date_n_a_pas_de_sens(self):
        query = parse_query("-date:2026-10")

        self.assertEqual(len(query.errors), 1)
        self.assertEqual((query.date_from, query.date_to), (None, None))


class MalformedTests(SimpleTestCase):
    def test_guillemet_non_ferme(self):
        query = parse_query('banc "résistance thermique')

        self.assertEqual(
            texts(query),
            [("banc", "word", False), ("résistance thermique", "phrase", False)],
        )
        self.assertEqual(len(query.errors), 1)
        self.assertIn("guillemet", query.errors[0].lower())

    def test_guillemet_non_ferme_dans_un_operateur(self):
        query = parse_query('projet:"Mon projet')

        self.assertEqual(query.projects, ["Mon projet"])
        self.assertEqual(len(query.errors), 1)

    def test_aucune_entree_ne_leve(self):
        for text in [
            '"',
            '""',
            "-",
            "--",
            ":",
            "a:",
            ":b",
            "-:",
            '-"',
            "*",
            '\\"',
            "\n\t",
        ]:
            with self.subTest(text=text):
                parse_query(text)

    def test_term_est_hashable_et_comparable(self):
        self.assertEqual(Term("a", "word"), Term("a", "word"))
