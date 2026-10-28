"""Tests de la recherche de note parts par projet et sujet."""

from django.test import TestCase
from django.urls import reverse

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
        html = response.content.decode()
        shown = [c for c in ("a1", "a2", "a3", "b1", "b2") if f"<p>{c}</p>" in html]
        return sorted(shown, key=lambda c: html.index(f"<p>{c}</p>"))

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

        self.assertContains(response, "Résistance thermique")

    def test_texte_libre_et_projet(self):
        """Le texte s'ajoute aux filtres : tous doivent être satisfaits."""
        NotePart.objects.create(
            note=Note.objects.get(date="2025-11-24"),
            project=self.beta,
            content="a2 chez Beta",
        )

        response = self.search(q="a2", projects=[self.beta.pk])

        self.assertEqual(self.contents(response), [])
        self.assertContains(response, "a2 chez Beta")
        self.assertNotContains(response, "<p>a2</p>")

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


class SubjectChoicesTests(SearchTestCase):
    url = reverse("note_taking:get_subjects")

    ALL = [
        "Alpha › Mesures",
        "Alpha › Mesures › Détail",
        "Alpha › thermique",
        "Beta › thermique",
    ]

    def choices(self, response) -> list[str]:
        """Les chemins proposés, avec leur projet."""
        return [
            label for _, label in response.context["form"].fields["subjects"].choices
        ]

    def test_chemins_tous_projets_tries_sans_vide(self):
        response = self.client.get(self.url)

        self.assertEqual(self.choices(response), self.ALL)

    def test_chemins_filtres_par_projet(self):
        response = self.client.get(self.url, {"projects": [self.beta.pk]})

        self.assertEqual(self.choices(response), ["Beta › thermique"])

    def test_formulaire_de_recherche_propose_tous_les_chemins(self):
        response = self.client.get(reverse("note_taking:notes_search"))

        self.assertEqual(self.choices(response), self.ALL)

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

        response = self.client.get(self.url, {"projects": [self.alpha.pk]})

        self.assertIn("Alpha › Rapports", self.choices(response))
        self.assertIn("Alpha › Rapports › Annuel", self.choices(response))
