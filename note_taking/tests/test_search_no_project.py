"""Le texte sans projet dans la recherche (#385, point 4) : l'opérateur
`sans:projet` et la case « Sans projet » de l'arbre « Projets et chemins »."""

import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note, Passage
from note_taking.search import search_passages
from note_taking.search_query import parse_query

URL = reverse("note_taking:notes_search")
FACET = re.compile(r'<span id="path-no-project-facet"[^>]*>.*?</span>\s*</span>', re.S)


class NoProjectQueryTests(SimpleTestCase):
    def test_sans_projet(self):
        query = parse_query("sans:projet banc")

        self.assertIs(query.no_project, True)
        self.assertEqual([term.text for term in query.terms], ["banc"])

    def test_exclusion_avec_un_projet(self):
        self.assertIs(parse_query("-sans:projet").no_project, False)

    def test_par_defaut_aucun_filtre(self):
        self.assertIsNone(parse_query("banc").no_project)

    def test_sans_casse_ni_accents(self):
        self.assertIs(parse_query("SANS:Projet").no_project, True)
        self.assertIs(parse_query('sans:"projet"').no_project, True)

    def test_filtre_seul_est_une_requete(self):
        self.assertTrue(parse_query("sans:projet"))
        self.assertTrue(parse_query("-sans:projet"))

    def test_valeur_inconnue_signalee_et_cherchee_telle_quelle(self):
        query = parse_query("sans:tag")

        self.assertIsNone(query.no_project)
        self.assertEqual([term.text for term in query.terms], ["sans:tag"])
        self.assertEqual(len(query.errors), 1)
        self.assertIn("sans:projet", query.errors[0])

    def test_valeur_vide_ignoree(self):
        query = parse_query("sans: banc")

        self.assertIsNone(query.no_project)
        self.assertEqual(query.errors, [])


class NoProjectFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = Project.objects.create(name="Alpha")
        cls.section = Section.objects.create(project=cls.alpha, name="Réunion")
        old = Note.objects.create(date="2026-10-01")
        new = Note.objects.create(date="2026-10-15")
        cls.loose_old = Passage.objects.create(note=old, content="banc vite noté")
        cls.loose_new = Passage.objects.create(note=new, content="appeler Paul")
        cls.filed = Passage.objects.create(
            note=new,
            project=cls.alpha,
            section=cls.section,
            position=1,
            content="banc rangé",
        )


class NoProjectSearchTests(NoProjectFixture):
    def search(self, text, **filters):
        return search_passages(parse_query(text), **filters)

    def test_operateur_garde_le_texte_sans_projet(self):
        self.assertEqual(
            set(self.search("sans:projet")), {self.loose_old, self.loose_new}
        )

    def test_operateur_avec_du_texte(self):
        self.assertEqual(self.search("sans:projet banc"), [self.loose_old])

    def test_exclusion_garde_le_texte_range(self):
        self.assertEqual(self.search("-sans:projet banc"), [self.filed])

    def test_operateur_et_projet_se_cumulent(self):
        """Un passage n'a pas de projet ou en a un : les deux ne donnent rien."""
        self.assertEqual(self.search("sans:projet projet:Alpha"), [])

    def test_case_seule(self):
        self.assertEqual(
            set(self.search("", no_project=True)), {self.loose_old, self.loose_new}
        )

    def test_case_et_projet_coche_l_un_ou_l_autre(self):
        """Comme les autres cases de l'arbre, réunies par « ou »."""
        found = self.search("banc", no_project=True, project_ids=[self.alpha.pk])

        self.assertEqual(set(found), {self.loose_old, self.filed})


class NoProjectPageTests(NoProjectFixture):
    def facet(self, response):
        return FACET.search(response.content.decode()).group()

    def test_case_dans_l_arbre_avec_son_compteur(self):
        response = self.client.get(URL)

        self.assertContains(response, 'name="no_project"')
        self.assertContains(response, "Sans projet")
        self.assertEqual(response.context["no_project_node"]["count"], 2)
        self.assertIn("(2", self.facet(response))

    def test_case_cochee_filtre_les_resultats(self):
        response = self.client.get(URL, {"no_project": "on"})

        self.assertEqual(
            set(response.context["results"]), {self.loose_old, self.loose_new}
        )
        self.assertRegex(response.content.decode(), r'name="no_project"[^>]*checked')

    def test_compteur_suit_la_requete(self):
        response = self.client.get(URL, {"q": "banc"})

        self.assertTrue(response.context["faceted"])
        self.assertEqual(response.context["no_project_node"]["count"], 1)

    def test_compteur_a_zero_attenue(self):
        response = self.client.get(URL, {"q": "rangé"})

        self.assertEqual(response.context["no_project_node"]["count"], 0)
        self.assertIn("data-zero", self.facet(response))

    def test_la_case_ne_change_pas_son_compteur(self):
        response = self.client.get(URL, {"q": "banc", "no_project": "on"})

        self.assertEqual(response.context["results"], [self.loose_old])
        self.assertEqual(response.context["no_project_node"]["count"], 1)
        nodes = {node.label: node for node in response.context["path_nodes"]}
        self.assertEqual(nodes["Alpha"].count, 1)

    def test_compteur_remplace_hors_bande_par_htmx(self):
        response = self.client.get(URL, {"q": "banc"}, headers={"HX-Request": "true"})

        facet = self.facet(response)
        self.assertIn('data-hx-swap-oob="true"', facet)
        self.assertNotIn('type="checkbox"', response.content.decode())

    def test_aucun_texte_sans_projet_pas_de_case(self):
        Passage.objects.filter(project__isnull=True).delete()

        response = self.client.get(URL)

        self.assertNotContains(response, 'name="no_project"')

    def test_aide_de_syntaxe(self):
        self.assertContains(self.client.get(URL), "<code>sans:projet</code>")
