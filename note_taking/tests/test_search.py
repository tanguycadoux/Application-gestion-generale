"""Tests de la recherche de note parts par projet et sujet."""

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from core.models import Project, Section
from note_taking.models import Note, NotePart


class SearchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = Project.objects.create(name="Alpha")
        cls.beta = Project.objects.create(name="Beta")
        cls.s_alpha_thermique = Section.objects.create(
            project=cls.alpha, name="thermique"
        )
        cls.s_beta_thermique = Section.objects.create(
            project=cls.beta, name="thermique"
        )
        cls.s_mesures = Section.objects.create(project=cls.alpha, name="Mesures")
        cls.s_detail = Section.objects.create(
            project=cls.alpha, parent=cls.s_mesures, name="Détail"
        )
        old = Note.objects.create(date="2025-11-23")
        new = Note.objects.create(date="2025-11-24")
        cls.alpha_thermique = NotePart.objects.create(
            note=old, project=cls.alpha, section=cls.s_alpha_thermique, content="a1"
        )
        cls.alpha_mesures = NotePart.objects.create(
            note=new, project=cls.alpha, section=cls.s_mesures, content="a2"
        )
        cls.beta_thermique = NotePart.objects.create(
            note=new, project=cls.beta, section=cls.s_beta_thermique, content="b1"
        )
        NotePart.objects.create(note=new, project=cls.beta, section=None, content="b2")
        NotePart.objects.create(
            note=new, project=cls.alpha, section=cls.s_detail, content="a3"
        )


class NotesSearchTests(SearchTestCase):
    url = reverse("note_taking:notes_search")

    def search(self, headers=None, **data):
        return self.client.get(self.url, data, headers=headers or {})

    def contents(self, response) -> list[str]:
        """Contenus des parts affichées, dans l'ordre de la page."""
        known = ("a1", "a2", "a3", "b1", "b2")
        return [
            p.content for p in response.context["results"] or [] if p.content in known
        ]

    def test_page_de_recherche(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["results"])

    def test_filtre_par_projet(self):
        response = self.search(projects=[self.alpha.pk])

        self.assertEqual(sorted(self.contents(response)), ["a1", "a2", "a3"])

    def test_filtre_par_sujet(self):
        response = self.search(subjects=[str(self.s_alpha_thermique.pk)])

        self.assertEqual(self.contents(response), ["a1"])

    def test_meme_sujet_de_deux_projets(self):
        response = self.search(
            subjects=[str(self.s_alpha_thermique.pk), str(self.s_beta_thermique.pk)]
        )

        self.assertEqual(sorted(self.contents(response)), ["a1", "b1"])

    def test_un_niveau_inclut_ses_descendants(self):
        """Filtrer sur « Mesures » cherche aussi « Mesures › Détail » (#296)."""
        response = self.search(subjects=[str(self.s_mesures.pk)])

        self.assertEqual(sorted(self.contents(response)), ["a2", "a3"])

    def test_un_sous_niveau_n_inclut_pas_son_parent(self):
        response = self.search(subjects=[str(self.s_detail.pk)])

        self.assertEqual(self.contents(response), ["a3"])

    def test_filtre_par_projet_et_sujet(self):
        response = self.search(
            projects=[self.beta.pk], subjects=[str(self.s_beta_thermique.pk)]
        )

        self.assertEqual(self.contents(response), ["b1"])

    def test_tri_par_date_decroissante(self):
        response = self.search(projects=[self.alpha.pk])

        # a2 et a3 sont de la même note, plus récente que celle de a1.
        self.assertEqual(sorted(self.contents(response)[:2]), ["a2", "a3"])
        self.assertEqual(self.contents(response)[2], "a1")

    def test_texte_libre(self):
        response = self.search(q="a2")

        self.assertEqual(self.contents(response), ["a2"])

    def test_texte_libre_sans_casse_ni_accents(self):
        NotePart.objects.create(
            note=Note.objects.get(date="2025-11-24"),
            project=self.alpha,
            content="Résistance thermique",
        )

        response = self.search(q="RESISTANCE")

        self.assertEqual(
            [p.content for p in response.context["results"]], ["Résistance thermique"]
        )

    def test_texte_libre_et_projet(self):
        """Le texte s'ajoute aux filtres : tous doivent être satisfaits."""
        NotePart.objects.create(
            note=Note.objects.get(date="2025-11-24"),
            project=self.beta,
            content="a2 chez Beta",
        )

        response = self.search(q="a2", projects=[self.beta.pk])

        self.assertEqual(self.contents(response), [])
        self.assertEqual(
            [p.content for p in response.context["results"]], ["a2 chez Beta"]
        )

    def test_texte_libre_sans_resultat(self):
        response = self.search(q="introuvable")

        self.assertEqual(response.context["results"], [])

    def test_texte_libre_trie_par_pertinence(self):
        note = Note.objects.get(date="2025-11-23")
        NotePart.objects.create(
            note=note, project=self.alpha, content="banc " + "autre " * 30
        )
        court = NotePart.objects.create(note=note, project=self.alpha, content="banc")

        response = self.search(q="banc")

        self.assertEqual(response.context["results"][0], court)

    def test_texte_vide_seul_ne_cherche_rien(self):
        response = self.search(q="  ")

        self.assertIsNone(response.context["results"])

    def test_texte_vide_avec_un_filtre(self):
        response = self.search(q="  ", projects=[self.alpha.pk])

        self.assertEqual(len(response.context["results"]), 3)

    def test_avant_toute_recherche_l_aide_s_affiche(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Aide sur la syntaxe de recherche")
        self.assertContains(
            response,
            '<details class="mt-4 rounded-xl border border-slate-300 p-3" open>',
        )
        self.assertNotContains(response, "Aucun résultat")

    def test_recherche_vide_montre_l_aide_pas_les_resultats(self):
        response = self.search(q="")

        self.assertIsNone(response.context["results"])
        self.assertNotContains(response, "Aucun résultat")

    def test_aucun_resultat_apres_une_recherche(self):
        response = self.search(q="introuvable")

        self.assertContains(response, "Aucun résultat.")
        self.assertEqual(response.context["results"], [])

    def test_aide_repliee_apres_une_recherche(self):
        response = self.search(q="a2")

        self.assertContains(response, "Aide sur la syntaxe de recherche")
        self.assertNotContains(response, 'p-3" open>')

    def test_la_recherche_est_dans_l_adresse(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'method="get"')
        self.assertNotContains(response, "csrfmiddlewaretoken")
        self.assertEqual(self.client.post(self.url, {"q": "a1"}).status_code, 405)

    def test_la_zone_garde_la_requete(self):
        response = self.search(q='projet:Alpha "a2"')

        self.assertContains(response, "projet:Alpha")

    def test_syntaxe_dans_la_zone(self):
        response = self.search(q="projet:beta -b2")

        self.assertEqual(self.contents(response), ["b1"])

    def test_requete_mal_formee_signalee(self):
        response = self.search(q="a1 date:demain")

        self.assertContains(response, "date:demain")
        self.assertContains(response, 'role="alert"')
        self.assertEqual(response.status_code, 200)

    def test_guillemet_non_ferme_signale(self):
        response = self.search(q='"a1')

        self.assertContains(response, "Guillemet non fermé")
        self.assertEqual(self.contents(response), ["a1"])

    def test_syntaxe_et_cases_se_cumulent(self):
        response = self.search(q="tag:inconnu", projects=[self.alpha.pk])

        self.assertEqual(self.contents(response), [])

    def test_requete_htmx_renvoie_les_resultats_seuls(self):
        response = self.search(
            headers={"HX-Request": "true"}, subjects=[str(self.s_mesures.pk)]
        )

        self.assertContains(response, "a2")
        self.assertNotContains(response, "<html")


class PathTreeTests(SearchTestCase):
    """L'arbre des chemins remplace la liste de cases à cocher (#302)."""

    url = reverse("note_taking:notes_search")

    ALL = [
        "Alpha › Mesures",
        "Alpha › Mesures › Détail",
        "Alpha › thermique",
        "Beta › thermique",
    ]

    def nodes(self, response):
        return response.context["path_nodes"]

    def labels(self, response) -> list[str]:
        """Les chemins proposés (cases), avec leur projet."""
        return [node.label for node in self.nodes(response) if node.selectable]

    def test_chemins_tous_projets_tries_sans_vide(self):
        self.assertEqual(self.labels(self.client.get(self.url)), self.ALL)

    def test_un_projet_est_un_titre_pas_une_case(self):
        response = self.client.get(self.url)

        projects = [n for n in self.nodes(response) if not n.selectable]
        self.assertEqual([n.name for n in projects], ["Alpha", "Beta"])

    def test_parent_propose_meme_sans_note_part(self):
        """Un niveau dont seuls les descendants servent reste proposé : on peut
        chercher dessous."""
        rapports = Section.objects.create(project=self.alpha, name="Rapports")
        annuel = Section.objects.create(
            project=self.alpha, parent=rapports, name="Annuel"
        )
        NotePart.objects.create(
            note=Note.objects.get(date="2025-11-24"),
            project=self.alpha,
            section=annuel,
            content="a4",
        )

        labels = self.labels(self.client.get(self.url))

        self.assertIn("Alpha › Rapports", labels)
        self.assertIn("Alpha › Rapports › Annuel", labels)

    def test_niveau_sans_note_part_absent(self):
        Section.objects.create(project=self.alpha, name="Vide")

        self.assertNotIn("Alpha › Vide", self.labels(self.client.get(self.url)))

    def test_compteurs_descendants_compris(self):
        counts = {
            node.label: node.count
            for node in self.nodes(self.client.get(self.url))
            if node.selectable
        }

        self.assertEqual(counts["Alpha › Mesures"], 2)
        self.assertEqual(counts["Alpha › Mesures › Détail"], 1)
        self.assertEqual(counts["Alpha › thermique"], 1)

    def test_cases_de_la_page(self):
        response = self.client.get(self.url)

        self.assertContains(
            response, f'name="subjects" value="{self.s_detail.pk}"', html=False
        )
        self.assertNotContains(response, "checked")

    def test_niveau_choisi_est_coche_et_ses_parents_ouverts(self):
        response = self.client.get(self.url, {"subjects": [self.s_detail.pk]})

        self.assertContains(response, f'value="{self.s_detail.pk}" checked', html=False)
        selected = [n for n in self.nodes(response) if n.selected]
        self.assertEqual([n.label for n in selected], ["Alpha › Mesures › Détail"])
        self.assertTrue(
            next(n for n in self.nodes(response) if n.name == "Mesures").open
        )

    def test_filtre_par_niveau_marche_toujours(self):
        response = self.client.get(self.url, {"subjects": [self.s_mesures.pk]})

        self.assertEqual(
            sorted(p.content for p in response.context["results"]), ["a2", "a3"]
        )

    def test_niveau_inconnu_ne_plante_pas(self):
        response = self.client.get(self.url, {"subjects": ["999999"]})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["results"])

    def test_plus_de_blocs_details_projets_et_chemins(self):
        html = self.client.get(self.url).content.decode()

        for title in ("Projets", "Chemins", "Sujets"):
            with self.subTest(title=title):
                self.assertNotRegex(html, rf"<summary[^>]*>\s*{title}\s*</summary>")

    def test_projets_en_cases_dans_l_arbre_un_seul_groupe(self):
        html = self.client.get(self.url).content.decode()

        self.assertEqual(html.count("<legend"), 1)
        self.assertIn(
            f'<input type="checkbox" id="path-project-{self.alpha.pk}"'
            f' name="projects" value="{self.alpha.pk}"',
            html,
        )
        self.assertNotIn("<legend class=\"mb-1 font-medium\">Projets</legend>", html)

    def test_projet_choisi_est_coche(self):
        html = self.client.get(self.url, {"projects": [self.alpha.pk]}).content.decode()

        self.assertRegex(
            html, rf'name="projects" value="{self.alpha.pk}"[^>]*\schecked'
        )

    def test_adresse_des_chemins_par_projet_supprimee(self):
        with self.assertRaises(NoReverseMatch):
            reverse("note_taking:get_subjects")
