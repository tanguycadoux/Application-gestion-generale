"""L'arbre des chemins réutilisable (#302) : construction des nœuds et composant."""

from typing import Any

from django.template import RequestContext, Template
from django.test import RequestFactory, SimpleTestCase, TestCase

from core.models import Project, Section
from core.path_tree import path_tree


def make_sections() -> dict[str, Any]:
    """Alpha › Mesures › Détail, Alpha › thermique, Beta › Mesures, Gamma (vide)."""
    alpha = Project.objects.create(name="Alpha")
    beta = Project.objects.create(name="beta")
    Project.objects.create(name="Gamma")
    mesures = Section.objects.create(project=alpha, name="Mesures")
    detail = Section.objects.create(project=alpha, parent=mesures, name="Détail")
    thermique = Section.objects.create(project=alpha, name="thermique")
    beta_mesures = Section.objects.create(project=beta, name="Mesures")
    return {
        "alpha": alpha,
        "beta": beta,
        "mesures": mesures,
        "detail": detail,
        "thermique": thermique,
        "beta_mesures": beta_mesures,
    }


class PathTreeTests(TestCase):
    def setUp(self):
        self.s = make_sections()

    def shape(self, nodes) -> list[tuple[str, int]]:
        return [(node.name, node.depth) for node in nodes]

    def test_projets_puis_chemins_parents_d_abord_tries_sans_casse(self):
        nodes = path_tree({})

        self.assertEqual(
            self.shape(nodes),
            [
                ("Alpha", 0),
                ("Mesures", 1),
                ("Détail", 2),
                ("thermique", 1),
                ("beta", 0),
                ("Mesures", 1),
            ],
        )

    def test_un_projet_sans_chemin_n_est_pas_propose(self):
        names = [node.name for node in path_tree({})]

        self.assertNotIn("Gamma", names)

    def test_un_projet_n_est_pas_selectionnable(self):
        nodes = path_tree({})

        self.assertFalse(nodes[0].selectable)
        self.assertIsNone(nodes[0].pk)
        self.assertTrue(nodes[1].selectable)

    def test_etiquette_complete_avec_le_projet(self):
        labels = {node.pk: node.label for node in path_tree({}) if node.selectable}

        self.assertEqual(labels[self.s["detail"].pk], "Alpha › Mesures › Détail")
        self.assertEqual(labels[self.s["beta_mesures"].pk], "beta › Mesures")

    def test_has_children(self):
        by_pk = {n.pk: n for n in path_tree({})}

        self.assertTrue(by_pk[self.s["mesures"].pk].has_children)
        self.assertFalse(by_pk[self.s["detail"].pk].has_children)
        self.assertFalse(by_pk[self.s["beta_mesures"].pk].has_children)
        self.assertTrue(path_tree({})[0].has_children)

    def test_compteur_descendants_compris(self):
        counts = {self.s["mesures"].pk: 2, self.s["detail"].pk: 3}

        by_pk = {n.pk: n for n in path_tree(counts) if n.selectable}
        by_name = {n.name: n for n in path_tree(counts) if not n.selectable}

        self.assertEqual(by_pk[self.s["mesures"].pk].count, 5)
        self.assertEqual(by_pk[self.s["detail"].pk].count, 3)
        self.assertEqual(by_pk[self.s["thermique"].pk].count, 0)
        self.assertEqual(by_name["Alpha"].count, 5)
        self.assertEqual(by_name["beta"].count, 0)

    def test_selection_et_niveaux_ouverts(self):
        nodes = path_tree({}, selected=[self.s["detail"].pk])
        by_pk = {n.pk: n for n in nodes if n.selectable}
        by_name = {n.name: n for n in nodes if not n.selectable}

        self.assertTrue(by_pk[self.s["detail"].pk].selected)
        self.assertFalse(by_pk[self.s["mesures"].pk].selected)
        # Ouvert d'office : un descendant est sélectionné. Pas celui qui l'est.
        self.assertTrue(by_pk[self.s["mesures"].pk].open)
        self.assertTrue(by_name["Alpha"].open)
        self.assertFalse(by_pk[self.s["detail"].pk].open)
        self.assertFalse(by_pk[self.s["thermique"].pk].open)
        self.assertFalse(by_name["beta"].open)

    def test_un_niveau_choisi_mais_pas_ses_enfants_reste_ferme(self):
        nodes = path_tree({}, selected=[self.s["mesures"].pk])

        self.assertFalse({n.pk: n for n in nodes}[self.s["mesures"].pk].open)

    def test_un_seul_projet_sans_noeud_de_projet(self):
        nodes = path_tree({}, project=self.s["alpha"])

        self.assertEqual(
            self.shape(nodes),
            [("Mesures", 0), ("Détail", 1), ("thermique", 0)],
        )
        self.assertTrue(all(node.selectable for node in nodes))

    def test_seulement_les_chemins_comptes_et_leurs_parents(self):
        counts = {self.s["detail"].pk: 1}

        nodes = path_tree(counts, only_counted=True)

        self.assertEqual(
            self.shape(nodes), [("Alpha", 0), ("Mesures", 1), ("Détail", 2)]
        )

    def test_seulement_les_comptes_garde_ce_qui_est_selectionne(self):
        nodes = path_tree({}, selected=[self.s["thermique"].pk], only_counted=True)

        self.assertEqual(self.shape(nodes), [("Alpha", 0), ("thermique", 1)])

    def test_les_enfants_sont_chaines(self):
        roots = [n for n in path_tree({}) if n.depth == 0]

        self.assertEqual([n.name for n in roots], ["Alpha", "beta"])
        self.assertEqual([c.name for c in roots[0].children], ["Mesures", "thermique"])

    def test_sans_chemin(self):
        Section.objects.all().delete()

        self.assertEqual(path_tree({}), [])

    def test_requetes_constantes(self):
        with self.assertNumQueries(1):
            path_tree({self.s["detail"].pk: 1}, selected=[self.s["detail"].pk])


def render(source: str, path: str = "/tasks/", **context) -> str:
    request = RequestFactory().get(path)
    template = Template("{% load ui %}" + source)
    return template.render(RequestContext(request, context))


class PathTreeComponentTests(TestCase):
    def setUp(self):
        self.s = make_sections()

    def tag(self, mode="link", selected=(), counts=None, path="/tasks/", **extra):
        nodes = path_tree(counts or {}, selected=selected)
        arguments = "".join(f" {key}={key!r}" for key in extra)
        return render(
            "{% path_tree nodes mode=mode param=param" + arguments + " %}",
            path,
            nodes=nodes,
            mode=mode,
            param="path",
        )

    def test_liste_imbriquee_semantique(self):
        html = self.tag()

        self.assertEqual(html.count("<ul"), 4)
        self.assertEqual(html.count("<details"), 3)
        self.assertIn('aria-label="Chemins"', html)
        self.assertIn("Alpha", html)

    def test_sans_noeud_pas_de_rendu(self):
        html = render("{% path_tree nodes mode='link' param='path' %}", nodes=[])

        self.assertEqual(html.strip(), "")

    def test_mode_lien_conserve_la_requete_et_remplace_le_parametre(self):
        html = self.tag(path="/tasks/?state=all&path=99&page=3")
        pk = self.s["thermique"].pk

        self.assertIn(f'href="/tasks/?state=all&amp;path={pk}"', html)
        self.assertNotIn("page=3", html)
        self.assertNotIn("path=99", html)

    def test_mode_lien_niveau_choisi_marque_et_lien_pour_le_retirer(self):
        pk = self.s["thermique"].pk

        html = self.tag(selected=[pk], path=f"/tasks/?state=all&path={pk}")

        self.assertIn('aria-current="true"', html)
        self.assertIn('href="/tasks/?state=all"', html)

    def test_mode_lien_sans_requete(self):
        html = self.tag(selected=[self.s["thermique"].pk], path="/tasks/?path=1")

        self.assertIn('href="/tasks/"', html)

    def test_un_projet_n_est_jamais_un_lien(self):
        html = self.tag()

        self.assertEqual(html.count("<a "), 4)

    def test_mode_cases(self):
        html = self.tag(mode="checkbox", selected=[self.s["detail"].pk])

        self.assertEqual(html.count('type="checkbox"'), 4)
        self.assertEqual(html.count("checked"), 1)
        self.assertIn(f'name="path" value="{self.s["detail"].pk}"', html)
        self.assertNotIn("<a ", html)

    def test_chaque_case_a_son_etiquette(self):
        html = self.tag(mode="checkbox")
        pk = self.s["thermique"].pk

        self.assertIn(f'id="path-{pk}"', html)
        self.assertIn(f'for="path-{pk}"', html)

    def test_niveaux_ouverts_d_office(self):
        html = self.tag(mode="checkbox", selected=[self.s["detail"].pk])

        # Alpha et Mesures, qui contiennent le niveau choisi ; pas beta.
        self.assertEqual(html.count("<details open"), 2)

    def test_aucun_niveau_ouvert_sans_selection(self):
        self.assertEqual(self.tag().count("<details open"), 0)

    def test_compteurs_affiches(self):
        html = self.tag(counts={self.s["mesures"].pk: 2, self.s["detail"].pk: 3})

        self.assertIn("(5)", html)
        self.assertIn("(3)", html)

    def test_un_compteur_nul_n_est_pas_affiche(self):
        html = self.tag(counts={})

        self.assertNotIn("(0)", html)

    def test_nom_echappe(self):
        Section.objects.create(
            project=self.s["alpha"], name='<script>alert("x")</script>'
        )

        html = self.tag()

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_mode_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            self.tag(mode="radio")


class PathTreeIndependenceTests(SimpleTestCase):
    def test_core_ne_connait_aucune_app(self):
        from pathlib import Path

        source = Path(__file__).parent.parent / "path_tree.py"
        text = source.read_text(encoding="utf-8")

        for app in ("note_taking", "todolist", "images"):
            self.assertNotIn(app, text)
