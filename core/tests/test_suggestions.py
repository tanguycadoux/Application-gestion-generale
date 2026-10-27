"""Listes de suggestions pour l'éditeur : projets et niveaux de chemin (#90)."""

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import section_for


class ProjectSuggestionsTests(TestCase):
    def names(self, **params) -> list[str]:
        response = self.client.get(reverse("core:project_suggestions"), params)
        self.assertEqual(response.status_code, 200)
        return [item["name"] for item in response.json()["results"]]

    def test_tous_les_projets_tries_sans_filtre(self):
        for name in ("ICONE", "ASTERICS", "école"):
            Project.objects.create(name=name, color="teal")

        self.assertEqual(self.names(), ["ASTERICS", "école", "ICONE"])

    def test_nom_et_couleur_de_chaque_projet(self):
        Project.objects.create(name="ASTERICS", color="rose")

        response = self.client.get(reverse("core:project_suggestions"))

        self.assertEqual(
            response.json(), {"results": [{"name": "ASTERICS", "color": "rose"}]}
        )

    def test_filtre_sans_casse_ni_accents(self):
        for name in ("ASTERICS", "Étude", "PDS1"):
            Project.objects.create(name=name, color="teal")

        self.assertEqual(self.names(q="ast"), ["ASTERICS"])
        # « é » et « É » sont la même lettre (le LOWER de SQLite ne le sait pas), et
        # l'accent ne se tape pas forcément.
        self.assertEqual(self.names(q="étu"), ["Étude"])
        self.assertEqual(self.names(q="ETUDE"), ["Étude"])

    def test_debut_du_nom_avant_le_milieu(self):
        for name in ("Alpha-ICONE", "ICONE", "Zeta ICONE"):
            Project.objects.create(name=name, color="teal")

        self.assertEqual(self.names(q="icone"), ["ICONE", "Alpha-ICONE", "Zeta ICONE"])

    def test_nombre_limite(self):
        for number in range(60):
            Project.objects.create(name=f"P{number:02d}", color="teal")

        self.assertEqual(len(self.names()), 50)

    def test_lecture_seule(self):
        response = self.client.post(reverse("core:project_suggestions"))

        self.assertEqual(response.status_code, 405)


class SectionSuggestionsTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="ASTERICS", color="teal")
        other = Project.objects.create(name="PDS1", color="rose")
        section_for(self.project, ["Réunion", "Préparation"])
        section_for(self.project, ["Réunion", "Bilan"])
        section_for(self.project, ["Analyse"])
        section_for(other, ["Autre"])

    def names(self, **params) -> list[str]:
        response = self.client.get(reverse("core:section_suggestions"), params)
        self.assertEqual(response.status_code, 200)
        return [item["name"] for item in response.json()["results"]]

    def test_premiers_niveaux_du_projet(self):
        self.assertEqual(self.names(projet="ASTERICS"), ["Analyse", "Réunion"])

    def test_niveaux_sous_un_chemin(self):
        self.assertEqual(
            self.names(projet="ASTERICS", chemin="Réunion"), ["Bilan", "Préparation"]
        )

    def test_filtre_sur_le_nom(self):
        self.assertEqual(
            self.names(projet="ASTERICS", chemin="Réunion", q="prép"), ["Préparation"]
        )

    def test_projet_et_niveaux_trouves_sans_tenir_compte_de_la_casse(self):
        self.assertEqual(
            self.names(projet="asterics", chemin="réunion"), ["Bilan", "Préparation"]
        )

    def test_barre_oblique_separe_les_niveaux_du_chemin(self):
        section_for(self.project, ["Réunion", "Préparation", "Salle"])

        self.assertEqual(
            self.names(projet="ASTERICS", chemin="Réunion/Préparation"), ["Salle"]
        )

    def test_projet_inconnu_ou_absent(self):
        self.assertEqual(self.names(projet="Inconnu"), [])
        self.assertEqual(self.names(), [])

    def test_chemin_inconnu(self):
        self.assertEqual(self.names(projet="ASTERICS", chemin="Inconnu"), [])

    def test_niveaux_d_un_autre_projet_non_proposes(self):
        self.assertNotIn("Autre", self.names(projet="ASTERICS"))

    def test_rien_n_est_cree(self):
        before = Section.objects.count()

        self.names(projet="ASTERICS", chemin="Nouveau/Niveau", q="x")

        self.assertEqual(Section.objects.count(), before)

    def test_lecture_seule(self):
        response = self.client.post(reverse("core:section_suggestions"))

        self.assertEqual(response.status_code, 405)
