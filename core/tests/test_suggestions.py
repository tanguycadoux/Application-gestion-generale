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
        self.assertEqual(self.names(project="ASTERICS"), ["Analyse", "Réunion"])

    def test_niveaux_sous_un_chemin(self):
        self.assertEqual(
            self.names(project="ASTERICS", path="Réunion"), ["Bilan", "Préparation"]
        )

    def test_filtre_sur_le_nom(self):
        self.assertEqual(
            self.names(project="ASTERICS", path="Réunion", q="prép"), ["Préparation"]
        )

    def test_projet_et_niveaux_trouves_sans_tenir_compte_de_la_casse(self):
        self.assertEqual(
            self.names(project="asterics", path="réunion"), ["Bilan", "Préparation"]
        )

    def test_barre_oblique_separe_les_niveaux_du_chemin(self):
        section_for(self.project, ["Réunion", "Préparation", "Salle"])

        self.assertEqual(
            self.names(project="ASTERICS", path="Réunion/Préparation"), ["Salle"]
        )

    def test_projet_inconnu_ou_absent(self):
        self.assertEqual(self.names(project="Inconnu"), [])
        self.assertEqual(self.names(), [])

    def test_chemin_inconnu(self):
        self.assertEqual(self.names(project="ASTERICS", path="Inconnu"), [])

    def test_niveaux_d_un_autre_projet_non_proposes(self):
        self.assertNotIn("Autre", self.names(project="ASTERICS"))


class ElsewhereSuggestionsTests(TestCase):
    """Les noms de niveau d'ailleurs : tous les projets, tous les niveaux (#91)."""

    def setUp(self):
        self.asterics = Project.objects.create(name="ASTERICS", color="teal")
        self.pds = Project.objects.create(name="PDS1", color="rose")
        section_for(self.asterics, ["Réunion", "Préparation"])
        section_for(self.asterics, ["Analyse"])
        section_for(self.pds, ["Autre", "Bilan"])
        section_for(self.pds, ["Réunion"])

    def get(self, **params) -> dict:
        response = self.client.get(reverse("core:section_suggestions"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def elsewhere(self, **params) -> dict[str, str]:
        return {item["name"]: item["where"] for item in self.get(**params)["elsewhere"]}

    def test_rien_sans_saisie(self):
        """Sans lettre tapée, la liste d'ailleurs noierait celle du niveau."""
        self.assertEqual(self.get(project="ASTERICS")["elsewhere"], [])

    def test_niveau_d_un_autre_projet_avec_son_chemin(self):
        self.assertEqual(
            self.elsewhere(project="ASTERICS", q="autre"), {"Autre": "PDS1 › Autre"}
        )

    def test_tous_les_niveaux_pas_seulement_ceux_du_meme_rang(self):
        """« Bilan » est au 2e niveau sous PDS1 : proposé sous un 1er niveau."""
        self.assertEqual(
            self.elsewhere(project="ASTERICS", q="bilan"),
            {"Bilan": "PDS1 › Autre › Bilan"},
        )

    def test_niveaux_du_meme_projet_hors_du_chemin_courant(self):
        self.assertEqual(
            self.elsewhere(project="ASTERICS", path="Analyse", q="prép"),
            {"Préparation": "ASTERICS › Réunion › Préparation"},
        )

    def test_casse_et_accents_ignores(self):
        self.assertIn("Préparation", self.elsewhere(project="PDS1", q="PREPARATION"))

    def test_nom_deja_propose_au_niveau_n_est_pas_repete(self):
        data = self.get(project="ASTERICS", q="réu")

        self.assertEqual([item["name"] for item in data["results"]], ["Réunion"])
        self.assertEqual(data["elsewhere"], [])

    def test_meme_nom_a_plusieurs_endroits_une_seule_entree(self):
        where = self.elsewhere(project="Inconnu", q="réunion")

        self.assertEqual(where, {"Réunion": "ASTERICS › Réunion (+1)"})

    def test_projet_ou_chemin_inconnu_propose_quand_meme_les_noms_d_ailleurs(self):
        """Un projet qu'on vient de taper n'existe pas encore : rien au niveau, mais
        les noms existants restent utiles."""
        for params in (
            {"project": "Nouveau"},
            {"project": "ASTERICS", "path": "Inconnu"},
            {},
        ):
            with self.subTest(params=params):
                data = self.get(q="analyse", **params)
                self.assertEqual(data["results"], [])
                self.assertEqual(
                    {item["name"] for item in data["elsewhere"]}, {"Analyse"}
                )


class ReadOnlyTests(TestCase):
    """Les listes de suggestions ne modifient rien (#90)."""

    def test_autres_methodes_que_get_refusees(self):
        for name in ("core:project_suggestions", "core:section_suggestions"):
            with self.subTest(view=name):
                self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    def test_aucun_niveau_cree_pour_un_projet_ou_un_chemin_inconnu(self):
        project = Project.objects.create(name="ASTERICS", color="teal")
        section_for(project, ["Réunion"])
        before = Section.objects.count()

        for params in (
            {"project": "Nouveau", "path": "A/B", "q": "x"},
            {"project": "ASTERICS", "path": "Nouveau/Niveau", "q": "x"},
        ):
            response = self.client.get(reverse("core:section_suggestions"), params)
            self.assertEqual(response.status_code, 200)

        self.assertEqual(Section.objects.count(), before)
