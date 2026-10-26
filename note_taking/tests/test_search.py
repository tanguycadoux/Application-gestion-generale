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
        alpha_thermique = Section.objects.create(project=cls.alpha, name="thermique")
        beta_thermique = Section.objects.create(project=cls.beta, name="thermique")
        mesures = Section.objects.create(project=cls.alpha, name="Mesures")
        old = Note.objects.create(date="2025-11-23")
        new = Note.objects.create(date="2025-11-24")
        cls.alpha_thermique = NotePart.objects.create(
            note=old, project=cls.alpha, section=alpha_thermique, content="a1"
        )
        cls.alpha_mesures = NotePart.objects.create(
            note=new, project=cls.alpha, section=mesures, content="a2"
        )
        cls.beta_thermique = NotePart.objects.create(
            note=new, project=cls.beta, section=beta_thermique, content="b1"
        )
        NotePart.objects.create(note=new, project=cls.beta, section=None, content="b2")


class NotesSearchTests(SearchTestCase):
    url = reverse("note_taking:notes_search")

    def search(self, headers=None, **data):
        return self.client.post(self.url, data, headers=headers or {})

    def contents(self, response) -> list[str]:
        """Contenus des parts affichées, dans l'ordre de la page."""
        html = response.content.decode()
        shown = [c for c in ("a1", "a2", "b1", "b2") if f"<p>{c}</p>" in html]
        return sorted(shown, key=lambda c: html.index(f"<p>{c}</p>"))

    def test_page_de_recherche(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["results"])

    def test_filtre_par_projet(self):
        response = self.search(projects=[self.alpha.pk])

        self.assertEqual(sorted(self.contents(response)), ["a1", "a2"])

    def test_filtre_par_sujet(self):
        response = self.search(subjects=["thermique"])

        self.assertEqual(sorted(self.contents(response)), ["a1", "b1"])

    def test_filtre_par_projet_et_sujet(self):
        response = self.search(projects=[self.beta.pk], subjects=["thermique"])

        self.assertEqual(self.contents(response), ["b1"])

    def test_tri_par_date_decroissante(self):
        response = self.search(projects=[self.alpha.pk])

        self.assertEqual(self.contents(response), ["a2", "a1"])

    def test_requete_htmx_renvoie_les_resultats_seuls(self):
        response = self.search(headers={"HX-Request": "true"}, subjects=["Mesures"])

        self.assertContains(response, "a2")
        self.assertNotContains(response, "<html")


class SubjectChoicesTests(SearchTestCase):
    url = reverse("note_taking:get_subjects")

    def choices(self, response) -> list[str]:
        return [
            value for value, _ in response.context["form"].fields["subjects"].choices
        ]

    def test_sujets_tous_projets_tries_sans_vide(self):
        response = self.client.post(self.url)

        self.assertEqual(self.choices(response), ["Mesures", "thermique"])

    def test_sujets_filtres_par_projet(self):
        response = self.client.post(self.url, {"projects": [self.beta.pk]})

        self.assertEqual(self.choices(response), ["thermique"])

    def test_formulaire_de_recherche_propose_tous_les_sujets(self):
        response = self.client.get(reverse("note_taking:notes_search"))

        self.assertEqual(self.choices(response), ["Mesures", "thermique"])
