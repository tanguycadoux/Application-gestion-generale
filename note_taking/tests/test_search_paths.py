"""`chemin:` qui ne trouve rien n'est plus muet (#368) : niveaux retenus, préfixe,
et suggestions quand aucun niveau ne correspond."""

from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.models import Note, Passage
from note_taking.search import search_passages
from note_taking.search_paths import path_reports
from note_taking.search_query import parse_query


class PathFixture(TestCase):
    """Données inventées de l'issue : deux chantiers, « Réunion de chantier » à
    deux profondeurs."""

    @classmethod
    def setUpTestData(cls):
        cls.nord = Project.objects.create(name="Chantier Nord")
        cls.sud = Project.objects.create(name="Chantier Sud")
        cls.nord_reunion = Section.objects.create(
            project=cls.nord, name="Réunion de chantier"
        )
        cls.nord_prepa = Section.objects.create(
            project=cls.nord, parent=cls.nord_reunion, name="Préparation"
        )
        cls.nord_suivi = Section.objects.create(project=cls.nord, name="Suivi")
        cls.lot = Section.objects.create(project=cls.sud, name="Lot 2")
        cls.sud_reunion = Section.objects.create(
            project=cls.sud, parent=cls.lot, name="Réunion de chantier"
        )
        note = Note.objects.create(date="2026-10-15")
        cls.p_nord = Passage.objects.create(
            note=note, project=cls.nord, section=cls.nord_prepa, content="banc"
        )
        cls.p_suivi = Passage.objects.create(
            note=note, project=cls.nord, section=cls.nord_suivi, content="banc"
        )
        cls.p_sud = Passage.objects.create(
            note=note, project=cls.sud, section=cls.sud_reunion, content="banc"
        )

    def search(self, text):
        return set(search_passages(parse_query(text)))

    def report(self, text):
        [report] = path_reports(text)
        return report

    def suggested(self, text):
        return [suggestion.q for suggestion in self.report(text).suggestions]


class PrefixTests(PathFixture):
    def test_prefixe_d_un_niveau(self):
        self.assertEqual(self.search("chemin:réunion*"), {self.p_nord, self.p_sud})

    def test_prefixe_sans_accents_ni_casse(self):
        self.assertEqual(self.search("chemin:REUN*"), {self.p_nord, self.p_sud})

    def test_prefixe_d_un_mot_du_nom(self):
        """Comme `mot*` dans le texte : un mot du nom commence par le préfixe."""
        self.assertEqual(self.search("chemin:chant*"), {self.p_nord, self.p_sud})

    def test_prefixe_du_dernier_niveau_seulement(self):
        self.assertEqual(
            self.search('chemin:"réunion de chantier/prépa*"'), {self.p_nord}
        )

    def test_prefixe_exclu(self):
        self.assertEqual(self.search("banc -chemin:sui*"), {self.p_nord, self.p_sud})

    def test_prefixe_au_milieu_d_un_mot_ne_trouve_rien(self):
        self.assertEqual(self.search("chemin:union*"), set())

    def test_sans_etoile_le_nom_reste_exact(self):
        self.assertEqual(self.search("chemin:réunion"), set())


class RetainedLevelsTests(PathFixture):
    def test_niveaux_retenus_avec_leur_projet(self):
        report = self.report('chemin:"reunion de chantier"')

        self.assertEqual(report.written, "reunion de chantier")
        self.assertFalse(report.negated)
        self.assertEqual(
            report.levels,
            [
                "Chantier Nord › Réunion de chantier",
                "Chantier Sud › Lot 2 › Réunion de chantier",
            ],
        )
        self.assertEqual(report.suggestions, [])

    def test_exclusion(self):
        report = self.report("-chemin:suivi")

        self.assertTrue(report.negated)
        self.assertEqual(report.levels, ["Chantier Nord › Suivi"])

    def test_un_bilan_par_chemin_dans_l_ordre(self):
        reports = path_reports("chemin:Suivi banc chemin:prépa*")

        self.assertEqual([r.written for r in reports], ["Suivi", "prépa*"])

    def test_sans_chemin_aucun_bilan(self):
        self.assertEqual(path_reports('banc projet:"Chantier Nord" tag:x'), [])
        self.assertEqual(path_reports(""), [])
        self.assertEqual(path_reports("chemin:"), [])


class SuggestionTests(PathFixture):
    def test_nom_partiel(self):
        report = self.report("chemin:reunion")

        self.assertEqual(report.levels, [])
        self.assertEqual(report.suggestions[0].q, 'chemin:"Réunion de chantier"')

    def test_meme_nom_dans_deux_projets_une_seule_suggestion(self):
        self.assertEqual(
            self.suggested("chemin:reunion"), ['chemin:"Réunion de chantier"']
        )

    def test_faute_de_frappe(self):
        self.assertEqual(
            self.suggested('chemin:"reunion de chantie"'),
            ['chemin:"Réunion de chantier"'],
        )

    def test_faute_dans_un_nom_court(self):
        self.assertEqual(self.suggested("chemin:suiv"), ["chemin:Suivi"])

    def test_guillemets_oublies(self):
        """« de chantier » est lu comme du texte : on propose les guillemets."""
        self.assertEqual(
            self.suggested("chemin:réunion de chantier")[0],
            'chemin:"réunion de chantier"',
        )

    def test_guillemets_oublies_suite_de_la_requete_gardee(self):
        self.assertEqual(
            self.suggested("chemin:réunion de chantier banc")[0],
            'chemin:"réunion de chantier" banc',
        )

    def test_projet_en_premier_niveau(self):
        self.assertEqual(
            self.suggested('chemin:"Chantier Nord/Réunion de chantier"')[0],
            'projet:"Chantier Nord" chemin:"Réunion de chantier"',
        )

    def test_projet_seul_en_chemin(self):
        self.assertEqual(
            self.suggested('chemin:"chantier sud"')[0], 'projet:"Chantier Sud"'
        )

    def test_plusieurs_niveaux_approchants(self):
        self.assertIn(
            'chemin:"Réunion de chantier/Préparation"',
            self.suggested('chemin:"reunion/preparatoin"'),
        )

    def test_le_reste_de_la_requete_est_garde(self):
        self.assertEqual(
            self.suggested("banc chemin:reunion tag:urgent"),
            ['banc chemin:"Réunion de chantier" tag:urgent'],
        )

    def test_exclusion_garde_son_signe(self):
        self.assertEqual(
            self.suggested("-chemin:reunion"), ['-chemin:"Réunion de chantier"']
        )

    def test_projet_en_premier_niveau_pas_pour_une_exclusion(self):
        """`-projet:A -chemin:B` n'exclut pas « A › B » mais tout A et tout B."""
        self.assertNotIn(
            '-projet:"Chantier Nord" -chemin:"Réunion de chantier"',
            self.suggested('-chemin:"Chantier Nord/Réunion de chantier"'),
        )

    def test_rien_d_approchant(self):
        self.assertEqual(self.suggested("chemin:zzzzzz"), [])

    def test_mot_trop_court_pour_un_nom_partiel(self):
        """« de » est dans tous les noms : pas de suggestion par nom partiel."""
        self.assertEqual(self.suggested("chemin:de"), [])

    def test_barre_dans_un_nom_doublee(self):
        Section.objects.create(project=self.nord, name="Rapport RT17/A")

        self.assertEqual(self.suggested("chemin:rapport"), ['chemin:"Rapport RT17//A"'])


class SearchPageTests(PathFixture):
    url = reverse("note_taking:notes_search")

    def test_niveaux_retenus_affiches(self):
        response = self.client.get(self.url, {"q": 'chemin:"reunion de chantier"'})

        self.assertContains(response, "2 niveaux")
        self.assertContains(response, "Chantier Sud › Lot 2 › Réunion de chantier")

    def test_aucun_niveau_signale_avec_suggestion(self):
        response = self.client.get(self.url, {"q": "chemin:reunion"})

        self.assertContains(response, "Aucun niveau ne s'appelle « reunion »")
        self.assertContains(response, "Essayer :")
        self.assertContains(response, "Aucun résultat.")

    def test_lien_de_suggestion(self):
        response = self.client.get(
            self.url, {"q": "chemin:reunion", "view": "document"}
        )
        html = response.content.decode()

        self.assertIn('chemin:"Réunion de chantier"', html.replace("&quot;", '"'))
        href = next(
            part.split('"')[0]
            for part in html.split('href="')[1:]
            if "chemin" in part.split('"')[0]
        )
        params = parse_qs(urlparse(href.replace("&amp;", "&")).query)
        self.assertEqual(params["q"], ['chemin:"Réunion de chantier"'])
        self.assertEqual(params["view"], ["document"])

    def test_resultats_htmx_avec_le_bilan(self):
        response = self.client.get(
            self.url, {"q": "chemin:reunion"}, headers={"HX-Request": "true"}
        )

        self.assertContains(response, "Aucun niveau ne s'appelle")

    def test_sans_chemin_pas_de_bilan(self):
        response = self.client.get(self.url, {"q": "banc"})

        self.assertEqual(response.context["path_reports"], [])
        self.assertNotContains(response, "Chemins de la requête")
