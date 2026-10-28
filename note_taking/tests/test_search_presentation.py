"""Présentation des résultats (#356) : fil d'Ariane, vue « document » regroupée par
date ou par chemin, sélecteur de vue."""

import re

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.search import (
    DEFAULT_GROUP,
    DEFAULT_VIEW,
    group_by_note,
    result_options,
    search_note_parts,
)
from note_taking.search_query import parse_query


class PresentationTestCase(TestCase):
    url = reverse("note_taking:notes_search")

    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.new = Note.objects.create(date="2026-10-15")
        cls.old = Note.objects.create(date="2026-09-10")
        cls.mesure = cls.part(cls.new, "banc de mesure", "Alpha › Réunion › Bilan")
        cls.test = cls.part(cls.new, "banc de test", "Alpha › Réunion")
        cls.ancien = cls.part(cls.old, "un banc ancien", "Alpha › Réunion")

    @classmethod
    def part(cls, note, content, heading_path):
        return NotePart.objects.create(
            note=note, project=cls.project, content=content, heading_path=heading_path
        )

    def get(self, **params):
        return self.client.get(self.url, {"q": "banc", **params})


class OptionsTests(TestCase):
    def test_valeurs_par_defaut(self):
        self.assertEqual(result_options({}), (DEFAULT_VIEW, DEFAULT_GROUP))
        self.assertEqual((DEFAULT_VIEW, DEFAULT_GROUP), ("extraits", "date"))

    def test_valeurs_valides(self):
        self.assertEqual(
            result_options({"view": "document", "group": "path"}), ("document", "path")
        )

    def test_valeurs_inconnues_remplacees(self):
        self.assertEqual(
            result_options({"view": "x", "group": "y"}), (DEFAULT_VIEW, DEFAULT_GROUP)
        )


class BreadcrumbTests(PresentationTestCase):
    def test_chaque_niveau_ascendant_est_un_lien_vers_sa_section(self):
        response = self.get(q="mesure")
        note_url = reverse("note_taking:note_detail", args=["2026-10-15"])

        self.assertContains(response, 'aria-label="Chemin du résultat"')
        self.assertContains(response, f'href="{note_url}#alpha"')
        self.assertContains(response, f'href="{note_url}#réunion"')
        # Le dernier niveau est le titre du résultat.
        self.assertContains(response, f'href="{note_url}#bilan"')

    def test_ancetres_dans_le_fil_pas_le_dernier(self):
        response = self.get(q="mesure")
        html = response.content.decode()
        crumbs = re.search(
            r'<nav[^>]*aria-label="Chemin du résultat".*?</nav>', html, re.DOTALL
        )

        self.assertIsNotNone(crumbs)
        self.assertIn("Alpha", crumbs[0])
        self.assertIn("Réunion", crumbs[0])
        self.assertNotIn("Bilan", crumbs[0])

    def test_projet_seul_pas_de_fil(self):
        self.part(self.new, "banc seul", "Alpha")

        response = self.get(q="seul")

        self.assertNotContains(response, 'aria-label="Chemin du résultat"')

    def test_attributs_du_titre_non_affiches(self):
        self.part(self.new, "banc attribué", "Alpha › Titre {#mon-id}")

        response = self.get(q="attribué")

        self.assertNotContains(response, "{#mon-id}")
        self.assertContains(response, "#mon-id")

    def test_les_niveaux_sont_dans_les_hits(self):
        query = parse_query("mesure")
        parts = search_note_parts(query)
        assert parts is not None

        hit = group_by_note(query, parts)[0].hits[0]

        self.assertEqual([c.title for c in hit.crumbs], ["Alpha", "Réunion", "Bilan"])
        self.assertEqual(hit.anchor, "bilan")


class SelectorTests(PresentationTestCase):
    def test_sélecteur_de_vue_garde_le_reste_de_l_adresse(self):
        response = self.get(projects=[self.project.pk])

        self.assertContains(response, 'aria-label="Présentation des résultats"')
        self.assertContains(response, "view=document")
        self.assertContains(response, f"projects={self.project.pk}")
        self.assertContains(response, "q=banc")

    def test_vue_courante_marquee(self):
        html = self.get().content.decode()

        self.assertRegex(html, r'aria-current="true"[^>]*>\s*Extraits')

    def test_regroupement_propose_seulement_en_vue_document(self):
        self.assertNotContains(self.get(), "Par chemin")
        self.assertContains(self.get(view="document"), "Par chemin")

    def test_pas_de_sélecteur_sans_résultat(self):
        self.assertNotContains(self.get(q="introuvable"), "Présentation des résultats")
        self.assertNotContains(self.client.get(self.url), "Présentation des résultats")


class DocumentByDateTests(PresentationTestCase):
    def test_document_rendu_comme_une_note(self):
        response = self.get(view="document")

        self.assertContains(response, "<p>banc de mesure</p>", html=True)
        self.assertNotContains(response, "<mark>")

    def test_un_titre_par_note_les_plus_recentes_d_abord(self):
        html = self.get(view="document").content.decode()
        new_url = reverse("note_taking:note_detail", args=["2026-10-15"])

        self.assertIn(
            f'<h2><a href="{new_url}">Note du jeudi 15 octobre 2026</a></h2>', html
        )
        self.assertLess(html.index("15 octobre 2026"), html.index("10 septembre 2026"))

    def test_projet_et_niveaux_en_titres_sans_repetition(self):
        html = self.get(view="document").content.decode()

        self.assertIn("<h3>Alpha</h3>", html)
        self.assertIn("<h4>Réunion</h4>", html)
        self.assertIn("<h5>Bilan</h5>", html)
        # Alpha n'est écrit qu'une fois par note, Réunion une fois de plus par retour.
        self.assertEqual(html.count("<h3>Alpha</h3>"), 2)

    def test_hierarchie_des_titres(self):
        # Les résultats s'insèrent sous le h1 de la page de recherche.
        html = self.get(view="document").content.decode()
        html = html.split('id="results"')[1]

        self.assertNotIn("<h1", html)
        levels = [int(n) for n in re.findall(r"<h([1-6])", html)]
        self.assertEqual(levels[0], 2)
        for before, after in zip(levels, levels[1:], strict=False):
            self.assertLessEqual(after, before + 1)

    def test_numerotation_sur_le_texte_assemble(self):
        table = "| a |\n|---|\n| 1 |\n\n: Légende {#tbl-%s}"
        self.part(self.new, table % "un", "Alpha › Tableaux")
        self.part(self.old, table % "deux", "Alpha › Tableaux")

        html = self.get(q="Légende", view="document").content.decode()

        self.assertIn("Table\u00a01", html)
        self.assertIn("Table\u00a02", html)

    def test_pas_de_bloc_details(self):
        html = self.get(view="document").content.decode()
        results = html.split('id="results"')[1]

        # Le seul bloc replié des résultats est l'aide de syntaxe, après eux.
        self.assertEqual(results.count("<details"), 1)
        self.assertLess(
            results.index("</nav>"), results.index("Aide sur la syntaxe de recherche")
        )


class DocumentByPathTests(PresentationTestCase):
    def test_arbre_projet_niveaux(self):
        html = self.get(view="document", group="path").content.decode()

        self.assertIn("<h2>Alpha</h2>", html)
        self.assertIn("<h3>Réunion</h3>", html)
        self.assertIn("<h4>Bilan</h4>", html)
        self.assertEqual(html.count("<h3>Réunion</h3>"), 1)

    def test_chaque_partie_precedee_de_sa_date_en_lien(self):
        html = self.get(view="document", group="path").content.decode()
        new_url = reverse("note_taking:note_detail", args=["2026-10-15"])

        self.assertIn(f'<a href="{new_url}#réunion">jeudi 15 octobre 2026</a>', html)
        self.assertIn("10 septembre 2026", html)

    def test_dates_les_plus_recentes_d_abord_sous_un_chemin(self):
        html = self.get(view="document", group="path").content.decode()

        self.assertLess(html.index("banc de test"), html.index("un banc ancien"))

    def test_regroupement_inconnu_retombe_sur_la_date(self):
        html = self.get(view="document", group="autre").content.decode()

        self.assertIn("Note du jeudi 15 octobre 2026", html)


class HtmxTests(PresentationTestCase):
    def test_partiel_htmx_garde_la_vue_document(self):
        response = self.client.get(
            self.url,
            {"q": "banc", "view": "document", "group": "path"},
            headers={"HX-Request": "true"},
        )

        self.assertContains(response, "<h2>Alpha</h2>")
        self.assertNotContains(response, "<html")


class ExtraitsUnchangedTests(PresentationTestCase):
    def test_vue_par_defaut_est_celle_des_extraits(self):
        response = self.get()

        self.assertContains(response, "<mark>banc</mark>")
        self.assertEqual(response.context["view"], "extraits")
