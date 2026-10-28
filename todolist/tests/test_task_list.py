"""La liste des tâches : un seul tableau arborescent, trié et filtré dans l'URL,
dont l'état (en cours, terminées, toutes, écartées) est un filtre (#294, #178)."""

import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from core.sections import section_for
from core.tables import Sort
from todolist.models import Todo

TODAY = timezone.localdate()


def days(n: int):
    return TODAY + timedelta(days=n)


class TaskListTestCase(TestCase):
    def setUp(self):
        self.alpha = Project.objects.create(name="ALPHA", color="teal")
        self.beta = Project.objects.create(name="BETA", color="rose")
        self.reunion = section_for(self.alpha, ["Réunion"])
        make = Todo.objects.create
        self.ete = make(
            title="Été à préparer",
            project=self.alpha,
            section=self.reunion,
            due_date=days(5),
            progress=20,
        )
        self.bilan = make(
            title="Bilan", project=self.beta, due_date=days(2), progress=60
        )
        self.sans_date = make(title="Zèbre", project=self.beta)
        self.sous_tache = make(
            title="Sous-tâche de zèbre", project=self.beta, parent=self.sans_date
        )
        self.finie = make(
            title="Finie",
            project=self.alpha,
            due_date=days(-3),
            done=True,
            progress=100,
        )
        self.ecartee = make(
            title="Écartée",
            project=self.alpha,
            created_from_note=True,
            note_part_date=TODAY,
            note_part_text="Écartée",
            note_state=Todo.NoteState.DISMISSED,
        )
        self.url = reverse("todolist:todo_list")

    def get(self, **params):
        return self.client.get(self.url, params)

    def titles(self, response) -> list[str]:
        """Les titres des tâches du tableau, dans l'ordre d'affichage."""
        html = response.content.decode()
        return re.findall(r'data-task-id="\d+".*?>([^<]+)</a>', html, re.DOTALL)

    def roots(self, response) -> list[str]:
        """Les titres des tâches racines : sans la sous-tâche du « Zèbre »."""
        return [t for t in self.titles(response) if t != "Sous-tâche de zèbre"]


class StateFilterTests(TaskListTestCase):
    def test_par_defaut_les_taches_en_cours(self):
        response = self.get()

        self.assertEqual(
            self.titles(response),
            ["Bilan", "Été à préparer", "Zèbre", "Sous-tâche de zèbre"],
        )
        self.assertNotContains(response, ">Finie<")

    def test_terminees(self):
        response = self.get(state="done")

        self.assertEqual(self.titles(response), ["Finie"])

    def test_toutes_sans_les_ecartees(self):
        response = self.get(state="all")

        self.assertEqual(
            self.titles(response),
            ["Finie", "Bilan", "Été à préparer", "Zèbre", "Sous-tâche de zèbre"],
        )

    def test_ecartees(self):
        response = self.get(state="dismissed")

        self.assertEqual(
            [row.task.title for row in response.context["dismissed_rows"]],
            ["Écartée"],
        )
        self.assertContains(response, "Rétablir")
        self.assertNotContains(response, ">Bilan<")

    def test_etat_inconnu_revient_a_en_cours(self):
        response = self.get(state="foo")

        self.assertEqual(response.context["state"], "open")
        self.assertIn("Bilan", self.titles(response))

    def test_titre_selon_l_etat(self):
        for state, heading in (
            ("open", "En cours"),
            ("done", "Terminées"),
            ("all", "Toutes les tâches"),
            ("dismissed", "Écartées"),
        ):
            with self.subTest(state=state):
                self.assertContains(self.get(state=state), f">{heading}")

    def test_aucune_tache_pour_cet_etat(self):
        Todo.objects.filter(done=True).delete()

        self.assertContains(self.get(state="done"), "Aucune tâche terminée.")

    def test_entonnoir_de_l_etat_dans_l_en_tete_de_la_colonne_tache(self):
        html = self.get().content.decode()

        self.assertIn('popovertarget="filters-title"', html)
        panel = html[html.index('id="filters-title"') :]
        self.assertRegex(
            panel, r'<input type="radio" name="state" value="open" checked>'
        )
        self.assertIn('name="state" value="dismissed"', panel)
        self.assertIn('name="state" value="all"', panel)

    def test_l_etat_par_defaut_n_est_pas_un_filtre_actif(self):
        html = self.get().content.decode()

        self.assertNotIn('aria-label="Filtres actifs"', html)
        self.assertNotIn("filtre actif", html)

    def test_un_autre_etat_est_un_filtre_actif_retirable(self):
        html = self.get(state="done").content.decode()

        self.assertIn("État : Terminées", html)
        self.assertIn("filtre actif", html)
        self.assertRegex(
            html, r'<input type="radio" name="state" value="done" checked>'
        )

    def test_lien_vers_les_ecartees_depuis_la_liste(self):
        html = self.get().content.decode()

        self.assertIn('href="?state=dismissed"', html)
        self.assertIn("1 tâche écartée", html)

    def test_pas_de_lien_sans_tache_ecartee(self):
        Todo.all_objects.filter(note_state=Todo.NoteState.DISMISSED).delete()

        self.assertNotIn("écartée", self.get().content.decode())

    def test_le_formulaire_de_confirmation_du_retablissement_est_garde(self):
        html = self.get(state="dismissed").content.decode()

        self.assertIn(f'popovertarget="restore-{self.ecartee.pk}"', html)
        self.assertIn(reverse("todolist:todo_restore", args=[self.ecartee.pk]), html)


class TaskFilterTests(TaskListTestCase):
    def test_titre_contenant_sans_casse_ni_accents(self):
        for text in ("ete", "ÉTÉ", "préparer"):
            with self.subTest(text=text):
                self.assertEqual(self.titles(self.get(title=text)), ["Été à préparer"])

    def test_projet_par_son_nom(self):
        response = self.get(project="BETA")

        self.assertEqual(
            self.titles(response), ["Bilan", "Zèbre", "Sous-tâche de zèbre"]
        )

    def test_projet_inconnu_ignore(self):
        self.assertEqual(len(self.titles(self.get(project="Inconnu"))), 4)

    def test_chemin_et_descendants(self):
        sub = section_for(self.alpha, ["Réunion", "Préparation"])
        Todo.objects.filter(pk=self.bilan.pk).update(section=sub)

        response = self.get(path=self.reunion.pk)

        self.assertEqual(self.titles(response), ["Bilan", "Été à préparer"])

    def test_chemin_inconnu_ou_invalide_ignore(self):
        self.assertEqual(len(self.titles(self.get(path=99999))), 4)
        self.assertEqual(len(self.titles(self.get(path="abc"))), 4)

    def test_filtres_combines_et_etat(self):
        response = self.get(state="all", project="ALPHA")

        self.assertEqual(self.titles(response), ["Finie", "Été à préparer"])

    def test_parent_garde_pour_le_contexte_et_attenue(self):
        response = self.get(title="sous-tâche")

        html = response.content.decode()
        self.assertEqual(self.titles(response), ["Zèbre", "Sous-tâche de zèbre"])
        parent = html[html.index(f'data-task-id="{self.sans_date.pk}"') :].split(
            "</tr>"
        )[0]
        child = html[html.index(f'data-task-id="{self.sous_tache.pk}"') :].split(
            "</tr>"
        )[0]
        self.assertIn("text-slate-500", parent)
        self.assertNotIn("text-slate-500", child)

    def test_panneau_de_la_colonne_tache_porte_les_quatre_filtres(self):
        html = self.get().content.decode()
        panel = html[html.index('id="filters-title"') :].split("</form>")[0]

        for name in ("state", "title", "project", "path"):
            with self.subTest(name=name):
                self.assertIn(f'name="{name}"', panel)

    def test_les_projets_gardent_leur_pastille_dans_le_panneau(self):
        html = self.get().content.decode()
        panel = html[html.index('id="filters-title"') :].split("</form>")[0]

        self.assertIn("bg-teal-500", panel)
        self.assertIn("bg-rose-500", panel)

    def test_resume_des_filtres(self):
        html = self.get(title="été", project="ALPHA").content.decode()

        self.assertIn("Titre : contient « été »", html)
        # La pastille du projet suit son libellé dans la puce retirable.
        self.assertRegex(html, r"Projet :\s*<span class=\"inline-flex[^>]*>.*?ALPHA")
        self.assertIn("Retirer tous les filtres", html)

    def test_sans_resultat_le_tableau_reste_pour_changer_les_filtres(self):
        response = self.get(title="introuvable")

        self.assertContains(response, 'id="filters-title"')
        self.assertContains(response, "Aucune tâche ne répond aux filtres.")

    def test_les_filtres_s_appliquent_aussi_aux_ecartees(self):
        Todo.all_objects.create(
            title="Autre écartée",
            project=self.beta,
            created_from_note=True,
            note_part_date=TODAY,
            note_part_text="Autre écartée",
            note_state=Todo.NoteState.DISMISSED,
        )

        response = self.get(state="dismissed", project="BETA")

        self.assertEqual(
            [row.task.title for row in response.context["dismissed_rows"]],
            ["Autre écartée"],
        )

    def test_le_panneau_des_ecartees_garde_l_etat_choisi(self):
        html = self.get(state="dismissed").content.decode()

        self.assertIn('id="filters-title"', html)
        self.assertRegex(
            html, r'<input type="radio" name="state" value="dismissed" checked>'
        )


class MultiProjectTests(TaskListTestCase):
    """Le filtre par projet : plusieurs projets cochés, réunis par « ou »."""

    def setUp(self):
        super().setUp()
        self.gamma = Project.objects.create(name="GAMMA", color="sky")
        Todo.objects.create(title="Tâche gamma", project=self.gamma)

    def test_union_des_projets_coches(self):
        response = self.get(project=["ALPHA", "GAMMA"])

        self.assertEqual(self.titles(response), ["Été à préparer", "Tâche gamma"])

    def test_aucun_projet_coche_les_montre_tous(self):
        self.assertEqual(len(self.titles(self.get(project=[]))), 5)

    def test_avec_l_etat_et_un_autre_filtre(self):
        response = self.get(state="all", project=["ALPHA", "BETA"], title="i")

        self.assertEqual(self.titles(response), ["Finie", "Bilan"])

    def test_s_applique_aux_ecartees(self):
        Todo.all_objects.create(
            title="Écartée gamma",
            project=self.gamma,
            created_from_note=True,
            note_part_date=TODAY,
            note_part_text="Écartée gamma",
            note_state=Todo.NoteState.DISMISSED,
        )

        response = self.get(state="dismissed", project=["GAMMA", "BETA"])

        self.assertEqual(
            [row.task.title for row in response.context["dismissed_rows"]],
            ["Écartée gamma"],
        )


class TaskSortTests(TaskListTestCase):
    def test_tri_par_defaut_par_echeance_sans_echeance_a_la_fin(self):
        response = self.get()

        self.assertEqual(response.context["sort"], Sort("due"))
        self.assertEqual(
            self.titles(response)[:3], ["Bilan", "Été à préparer", "Zèbre"]
        )

    def test_echeance_decroissante_garde_les_sans_echeance_a_la_fin(self):
        response = self.get(sort="-due")

        self.assertEqual(
            self.titles(response)[:3], ["Été à préparer", "Bilan", "Zèbre"]
        )

    def test_par_titre(self):
        self.assertEqual(
            self.roots(self.get(sort="title")),
            ["Bilan", "Été à préparer", "Zèbre"],
        )
        self.assertEqual(
            self.roots(self.get(sort="-title")),
            ["Zèbre", "Été à préparer", "Bilan"],
        )

    def test_par_avancement(self):
        self.assertEqual(
            self.roots(self.get(sort="progress")),
            ["Zèbre", "Été à préparer", "Bilan"],
        )
        self.assertEqual(
            self.roots(self.get(sort="-progress")),
            ["Bilan", "Été à préparer", "Zèbre"],
        )

    def test_les_sous_taches_restent_sous_leur_parent(self):
        for sort in ("title", "-title", "due", "-due", "progress", "-progress"):
            with self.subTest(sort=sort):
                titles = self.titles(self.get(sort=sort))

                self.assertEqual(
                    titles.index("Sous-tâche de zèbre"), titles.index("Zèbre") + 1
                )

    def test_les_sous_taches_se_trient_entre_elles(self):
        Todo.objects.create(
            title="Autre enfant", project=self.beta, parent=self.sans_date, progress=50
        )

        by_title = self.titles(self.get(sort="title"))
        by_title_desc = self.titles(self.get(sort="-title"))

        self.assertLess(
            by_title.index("Autre enfant"), by_title.index("Sous-tâche de zèbre")
        )
        self.assertGreater(
            by_title_desc.index("Autre enfant"),
            by_title_desc.index("Sous-tâche de zèbre"),
        )

    def test_tri_inconnu_revient_au_tri_par_defaut(self):
        response = self.get(sort="foo")

        self.assertEqual(response.context["sort"], Sort("due"))

    def test_en_tetes_triables_avec_aria_sort(self):
        html = self.get().content.decode()

        self.assertIn('aria-sort="ascending"', html)
        self.assertIn('href="?sort=-due"', html)
        self.assertIn('href="?sort=title"', html)
        self.assertIn('href="?sort=progress"', html)

    def test_le_tri_garde_les_filtres_et_inversement(self):
        html = self.get(project="BETA", sort="title").content.decode()

        self.assertIn(
            "project=BETA&amp;sort=-title",
            html.replace(
                "sort=-title&amp;project=BETA", "project=BETA&amp;sort=-title"
            ),
        )
        self.assertIn('<input type="hidden" name="sort" value="title">', html)

    def test_detail_d_un_parent_garde_son_tri_par_echeance(self):
        Todo.objects.create(
            title="Tard", project=self.beta, parent=self.sans_date, due_date=days(9)
        )
        Todo.objects.create(
            title="Tôt", project=self.beta, parent=self.sans_date, due_date=days(1)
        )

        html = self.client.get(
            reverse("todolist:todo_detail", args=[self.sans_date.pk])
        ).content.decode()

        self.assertLess(html.index(">Tôt<"), html.index(">Tard<"))
        self.assertLess(html.index(">Tard<"), html.index(">Sous-tâche de zèbre<"))


class PathTreeFilterTests(TaskListTestCase):
    """Projets et chemins dans un seul arbre à cases (#302)."""

    def setUp(self):
        super().setUp()
        self.prep = section_for(self.alpha, ["Réunion", "Préparation"])
        Todo.objects.filter(pk=self.ete.pk).update(section=self.prep)

    def panel(self, **params) -> str:
        html = self.get(**params).content.decode()
        return html[html.index('id="filters-title"') :].split("</form>")[0]

    def test_un_seul_groupe_projets_et_chemins_en_cases(self):
        panel = self.panel()

        self.assertEqual(panel.count("Projets et chemins</legend>"), 1)
        self.assertIn(f'name="project" value="{self.alpha.name}"', panel)
        self.assertIn(f'name="path" value="{self.reunion.pk}"', panel)
        self.assertNotIn('type="radio" name="path"', panel)

    def test_projets_et_chemins_coches_sont_unis(self):
        response = self.get(project="BETA", path=self.prep.pk)

        self.assertEqual(
            self.titles(response),
            ["Bilan", "Été à préparer", "Zèbre", "Sous-tâche de zèbre"],
        )

    def test_plusieurs_chemins_coches(self):
        Todo.objects.filter(pk=self.bilan.pk).update(
            section=section_for(self.beta, ["Suivi"])
        )
        suivi = section_for(self.beta, ["Suivi"])

        response = self.get(path=[self.prep.pk, suivi.pk])

        self.assertEqual(self.titles(response), ["Bilan", "Été à préparer"])

    def test_compteurs_selon_l_etat_affiche(self):
        en_cours = self.panel()
        terminees = self.panel(state="done")

        # ALPHA : 1 tâche en cours (la terminée et l'écartée ne comptent pas).
        self.assertRegex(
            en_cours, r"ALPHA</span>\s*</span>\s*</label>\s*<span[^>]*>\(1\)"
        )
        self.assertRegex(
            terminees, r"ALPHA</span>\s*</span>\s*</label>\s*<span[^>]*>\(1\)"
        )
        self.assertNotIn("Réunion", terminees)

    def test_arbre_des_ecartees_compte_les_ecartees(self):
        panel = self.panel(state="dismissed")

        self.assertIn('name="project" value="ALPHA"', panel)
        self.assertNotIn('name="project" value="BETA"', panel)

    def test_niveau_vide_dans_l_etat_reste_un_filtre_valide(self):
        response = self.get(state="done", path=self.reunion.pk)

        self.assertContains(response, "Aucune tâche ne répond aux filtres.")

    def test_puces_retirables_une_par_choix(self):
        html = self.get(project="BETA", path=self.prep.pk).content.decode()

        self.assertIn("Chemin : ALPHA › Réunion › Préparation", html)
        self.assertRegex(html, r"Projet :\s*<span class=\"inline-flex[^>]*>.*?BETA")
