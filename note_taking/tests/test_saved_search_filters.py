"""Les cases de l'arbre s'enregistrent avec la recherche (#380)."""

import re
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from note_taking.exceptions import SavedSearchError
from note_taking.models import SavedSearch
from note_taking.saved_searches import save_search, search_url

SEARCH = reverse("note_taking:notes_search")
CREATE = reverse("note_taking:saved_search_create")


def params(url):
    return parse_qs(urlparse(url).query)


class Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.nord = Project.objects.create(name="Chantier Nord")
        cls.sud = Project.objects.create(name="Chantier Sud")
        cls.reunion = Section.objects.create(project=cls.nord, name="Réunion")
        cls.prepa = Section.objects.create(
            project=cls.nord, parent=cls.reunion, name="Préparation"
        )


class SaveFiltersTests(Fixture):
    def test_cases_enregistrees(self):
        saved = save_search("A", "banc", [self.sud.pk], [self.prepa.pk])

        self.assertEqual(list(saved.projects.all()), [self.sud])
        self.assertEqual(list(saved.sections.all()), [self.prepa])

    def test_cases_seules_sans_texte(self):
        saved = save_search("A", "", sections=[self.reunion.pk])

        self.assertEqual(saved.q, "")
        self.assertEqual(list(saved.sections.all()), [self.reunion])

    def test_rien_du_tout_refuse(self):
        with self.assertRaisesMessage(SavedSearchError, "Rien à enregistrer"):
            save_search("A", " ", [], [])

    def test_case_inconnue_ignoree(self):
        saved = save_search("A", "banc", [9999], [9999])

        self.assertFalse(saved.projects.exists())
        self.assertFalse(saved.sections.exists())

    def test_adresse_complete(self):
        saved = save_search(
            "A", "banc", [self.sud.pk], [self.prepa.pk, self.reunion.pk]
        )

        self.assertEqual(
            params(search_url(saved)),
            {
                "q": ["banc"],
                "projects": [str(self.sud.pk)],
                "subjects": sorted([str(self.prepa.pk), str(self.reunion.pk)]),
            },
        )

    def test_adresse_sans_case_inchangee(self):
        self.assertEqual(search_url(save_search("A", "banc")), SEARCH + "?q=banc")

    def test_niveau_supprime_retire_de_la_recherche(self):
        saved = save_search("A", "banc", sections=[self.prepa.pk])
        self.prepa.delete()

        self.assertEqual(search_url(saved), SEARCH + "?q=banc")


class CreateViewTests(Fixture):
    def test_creer_avec_les_cases(self):
        response = self.client.post(
            CREATE,
            {
                "name": "Réunions",
                "q": "banc",
                "projects": [self.sud.pk],
                "subjects": [self.reunion.pk],
            },
        )

        saved = SavedSearch.objects.get()
        self.assertEqual(list(saved.sections.all()), [self.reunion])
        self.assertEqual(
            params(response["Location"]),
            {
                "q": ["banc"],
                "projects": [str(self.sud.pk)],
                "subjects": [str(self.reunion.pk)],
            },
        )

    def test_erreur_garde_les_cases_dans_l_adresse(self):
        response = self.client.post(
            CREATE, {"name": " ", "q": "", "subjects": [self.reunion.pk]}
        )

        self.assertEqual(
            params(response["Location"]), {"subjects": [str(self.reunion.pk)]}
        )

    def test_supprimer_revient_avec_les_cases(self):
        saved = SavedSearch.objects.create(name="A", q="x")
        url = reverse("note_taking:saved_search_delete", args=[saved.pk])

        response = self.client.post(f"{url}?q=banc&subjects={self.reunion.pk}")

        self.assertEqual(
            params(response["Location"]),
            {"q": ["banc"], "subjects": [str(self.reunion.pk)]},
        )


class PageTests(Fixture):
    def test_message_absent_quand_seul_l_arbre_filtre(self):
        response = self.client.get(SEARCH, {"subjects": [self.reunion.pk]})

        html = response.content.decode()
        message = re.search(r"<p[^>]*data-saved-search-empty[^>]*>", html).group()
        self.assertIn("hidden", message)
        form = re.search(
            r"<form[^>]*data-saved-search-form[^>]*>", response.content.decode()
        ).group()
        self.assertNotIn("hidden", form)

    def test_cases_cachees_dans_le_formulaire_d_enregistrement(self):
        html = self.client.get(
            SEARCH,
            {"q": "banc", "projects": [self.sud.pk], "subjects": [self.prepa.pk]},
        ).content.decode()
        form = html[html.index("data-saved-search-form") :]
        form = form[: form.index("</form>")]

        self.assertIn(f'name="projects" value="{self.sud.pk}"', form)
        self.assertIn(f'name="subjects" value="{self.prepa.pk}"', form)

    def test_nom_propose_d_apres_les_niveaux_sans_texte(self):
        response = self.client.get(SEARCH, {"subjects": [self.prepa.pk]})

        self.assertContains(
            response, 'name="name" value="Chantier Nord › Réunion › Préparation"'
        )

    def test_nom_propose_d_apres_le_texte(self):
        response = self.client.get(SEARCH, {"q": "banc", "subjects": [self.prepa.pk]})

        self.assertContains(response, 'name="name" value="banc"')

    def test_recherche_courante_selon_texte_et_cases(self):
        saved = save_search("Avec cases", "banc", sections=[self.reunion.pk])
        save_search("Sans case", "banc")

        html = self.client.get(
            SEARCH, {"q": "banc", "subjects": [self.reunion.pk]}
        ).content.decode()

        current = re.findall(
            r'<a href="[^"]*" aria-current="true"[^>]*>([^<]*)</a>', html
        )
        self.assertEqual(current, [saved.name])

    def test_lien_de_la_recherche_avec_ses_cases(self):
        save_search("Avec cases", "banc", sections=[self.reunion.pk])

        html = self.client.get(SEARCH).content.decode()

        self.assertIn(f"subjects={self.reunion.pk}", html)

    def test_sans_rien_formulaire_cache_et_message(self):
        response = self.client.get(SEARCH)

        self.assertContains(
            response, "Lancer une recherche pour pouvoir l'enregistrer."
        )
        form = re.search(
            r"<form[^>]*data-saved-search-form[^>]*>", response.content.decode()
        ).group()
        self.assertIn("hidden", form)
