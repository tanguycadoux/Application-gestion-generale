"""L'arbre « Projets et chemins » suit la requête (#380) : compteurs du résultat,
niveaux retenus par `chemin:` marqués."""

import re

from django.urls import reverse

from note_taking.tests.test_search_paths import PathFixture

URL = reverse("note_taking:notes_search")


def nodes_of(response):
    return {node.label: node for node in response.context["path_nodes"]}


class FacetCountTests(PathFixture):
    def test_sans_requete_les_compteurs_de_toute_la_base(self):
        nodes = nodes_of(self.client.get(URL))

        self.assertEqual(nodes["Chantier Nord"].count, 2)
        self.assertFalse(self.client.get(URL).context["faceted"])

    def test_compteurs_du_resultat_de_la_requete(self):
        response = self.client.get(URL, {"q": 'chemin:"réunion de chantier"'})
        nodes = nodes_of(response)

        self.assertTrue(response.context["faceted"])
        self.assertEqual(nodes["Chantier Nord"].count, 1)
        self.assertEqual(nodes["Chantier Nord › Suivi"].count, 0)
        self.assertEqual(nodes["Chantier Sud › Lot 2"].count, 1)

    def test_niveau_a_zero_reste_visible_et_attenue(self):
        response = self.client.get(URL, {"q": 'chemin:"réunion de chantier"'})

        self.assertIn("Chantier Nord › Suivi", nodes_of(response))
        facet = re.search(
            rf'<span id="path-{self.nord_suivi.pk}-facet"[^>]*>',
            response.content.decode(),
        ).group()
        self.assertIn("data-zero", facet)

    def test_les_cases_cochees_ne_changent_pas_les_compteurs(self):
        """Sinon cocher un niveau mettrait tous les autres à 0."""
        response = self.client.get(URL, {"q": "banc", "subjects": [self.nord_suivi.pk]})
        nodes = nodes_of(response)

        self.assertEqual(response.context["results"], [self.p_suivi])
        self.assertEqual(nodes["Chantier Sud"].count, 1)
        self.assertEqual(nodes["Chantier Nord › Réunion de chantier"].count, 1)

    def test_aucun_resultat_tout_a_zero(self):
        nodes = nodes_of(self.client.get(URL, {"q": "introuvable"}))

        self.assertEqual({node.count for node in nodes.values()}, {0})
        self.assertIn("Chantier Nord › Suivi", nodes)


class MarkedLevelTests(PathFixture):
    def test_niveaux_retenus_marques_et_ouverts_pas_coches(self):
        nodes = nodes_of(self.client.get(URL, {"q": 'chemin:"réunion de chantier"'}))

        for label in [
            "Chantier Nord › Réunion de chantier",
            "Chantier Sud › Lot 2 › Réunion de chantier",
        ]:
            self.assertTrue(nodes[label].marked, label)
            self.assertFalse(nodes[label].selected, label)
        self.assertTrue(nodes["Chantier Sud › Lot 2"].open)
        self.assertFalse(nodes["Chantier Nord › Suivi"].marked)

    def test_un_chemin_exclu_n_est_pas_marque(self):
        nodes = nodes_of(self.client.get(URL, {"q": "-chemin:suivi"}))

        self.assertFalse(nodes["Chantier Nord › Suivi"].marked)


class HtmxFacetTests(PathFixture):
    def get(self, params):
        return self.client.get(URL, params, headers={"HX-Request": "true"})

    def test_compteurs_remplaces_hors_des_resultats(self):
        html = self.get({"q": "chemin:suivi"}).content.decode()

        facet = re.search(
            rf'<span id="path-{self.nord_suivi.pk}-facet"[^>]*>', html
        ).group()
        self.assertIn('data-hx-swap-oob="true"', facet)
        self.assertIn("data-marked", facet)

    def test_l_arbre_lui_meme_n_est_pas_renvoye(self):
        """Les cases et les niveaux ouverts restent tels quels (focus, repli)."""
        html = self.get({"q": "banc"}).content.decode()

        self.assertNotIn('type="checkbox"', html)

    def test_page_complete_sans_echange_hors_bande(self):
        html = self.client.get(URL, {"q": "banc"}).content.decode()

        self.assertNotIn("hx-swap-oob", html)

    def test_script_qui_ouvre_les_niveaux_marques(self):
        self.assertContains(self.client.get(URL), "note_taking/search_tree.js")
