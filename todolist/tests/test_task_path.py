"""Le chemin d'une tâche : saisi en texte avec autocomplétion, affiché en « › »,
et filtre de la liste sur un niveau, descendants compris (#298)."""

from django.test import TestCase
from django.urls import reverse

from core.models import Project, Section
from core.sections import levels, section_for
from todolist.forms import NoteReviewForm, TodoForm
from todolist.models import Todo


class PathTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P")

    def data(self, **fields) -> dict:
        return {
            "title": "T",
            "priority": "medium",
            "progress": 0,
            "project": self.project.pk,
            **fields,
        }

    def save(self, **fields) -> Todo:
        form = TodoForm(data=self.data(**fields))
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()


class PathFieldTests(PathTestCase):
    def test_champ_chemin_avec_son_libelle(self):
        form = TodoForm()

        self.assertEqual(form.fields["section_path"].label, "Chemin")
        self.assertNotIn("section", form.fields)

    def test_chemin_cree_sous_le_projet(self):
        todo = self.save(section_path="Réunion/Préparation")

        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Réunion", "Préparation"])
        self.assertEqual(todo.section.project, self.project)

    def test_chemin_connu_repris_casse_ignoree(self):
        known = section_for(self.project, ["Réunion", "Préparation"])

        todo = self.save(section_path="réunion / PRÉPARATION")

        self.assertEqual(todo.section, known)
        self.assertEqual(Section.objects.count(), 2)

    def test_sans_chemin(self):
        todo = self.save(section_path="")

        self.assertIsNone(todo.section)

    def test_double_barre_est_une_barre_litterale(self):
        todo = self.save(section_path="Rapport RT17//A/Suite")

        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Rapport RT17/A", "Suite"])

    def test_espaces_et_niveaux_vides_ignores(self):
        todo = self.save(section_path="  Réunion  / /  Suite / ")

        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Réunion", "Suite"])

    def test_niveau_trop_long_refuse(self):
        form = TodoForm(data=self.data(section_path="A" * 201))

        self.assertFalse(form.is_valid())
        self.assertIn("200 caractères", str(form.errors["section_path"]))

    def test_rien_n_est_cree_si_le_formulaire_est_invalide(self):
        form = TodoForm(data=self.data(title="", section_path="Nouveau/Chemin"))

        self.assertFalse(form.is_valid())
        self.assertFalse(Section.objects.exists())

    def test_meme_chemin_sous_deux_projets(self):
        other = Project.objects.create(name="Q")
        first = self.save(section_path="Réunion")

        form = TodoForm(data=self.data(project=other.pk, section_path="Réunion"))
        self.assertTrue(form.is_valid(), form.errors)
        second = form.save()

        self.assertNotEqual(first.section, second.section)
        assert second.section is not None
        self.assertEqual(second.section.project, other)

    def test_changer_de_projet_replace_le_chemin(self):
        todo = self.save(section_path="Réunion")
        other = Project.objects.create(name="Q")

        form = TodoForm(
            data=self.data(project=other.pk, section_path="Réunion"), instance=todo
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        todo.refresh_from_db()
        assert todo.section is not None
        self.assertEqual(todo.section.project, other)

    def test_enlever_le_chemin(self):
        todo = self.save(section_path="Réunion")

        form = TodoForm(data=self.data(section_path=""), instance=todo)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        todo.refresh_from_db()
        self.assertIsNone(todo.section)

    def test_valeur_initiale_a_ressaisir_a_l_identique(self):
        todo = self.save(section_path="Rapport RT17//A/Suite")

        form = TodoForm(instance=todo)

        self.assertEqual(form.initial["section_path"], "Rapport RT17//A/Suite")

    def test_tags_enregistres_avec_le_chemin(self):
        from core.models import Tag

        tag = Tag.objects.create(name="urgent")

        todo = self.save(section_path="Réunion", tags=[tag.pk])

        self.assertEqual(list(todo.tags.all()), [tag])


class DatalistTests(PathTestCase):
    def test_autocompletion_par_une_liste_native(self):
        section_for(self.project, ["Réunion", "Préparation"])

        html = str(TodoForm()["section_path"])

        self.assertIn('list="id_section_path-chemins"', html)
        self.assertIn('<datalist id="id_section_path-chemins">', html)
        self.assertIn('<option value="Réunion/Préparation" label="P">', html)
        self.assertIn('<option value="Réunion" label="P">', html)

    def test_un_chemin_de_deux_projets_une_seule_option(self):
        other = Project.objects.create(name="Q")
        section_for(self.project, ["Réunion"])
        section_for(other, ["Réunion"])

        html = str(TodoForm()["section_path"])

        self.assertEqual(html.count('<option value="Réunion"'), 1)
        self.assertIn('label="P, Q"', html)

    def test_barre_litterale_echappee_dans_les_options(self):
        section_for(self.project, ["Rapport RT17/A"])

        html = str(TodoForm()["section_path"])

        self.assertIn('<option value="Rapport RT17//A"', html)

    def test_nombre_de_requetes_constant(self):
        for index in range(10):
            section_for(self.project, [f"N{index}", "Sous"])

        with self.assertNumQueries(1):
            str(TodoForm()["section_path"])

    def test_sans_chemin_liste_vide(self):
        html = str(TodoForm()["section_path"])

        self.assertIn('<datalist id="id_section_path-chemins"></datalist>', html)


class NoteReviewFormTests(PathTestCase):
    def test_le_bilan_saisit_le_chemin_aussi(self):
        todo = Todo.objects.create(title="T", project=self.project)
        form = NoteReviewForm(
            data={
                "due_date": "",
                "priority": "medium",
                "project": self.project.pk,
                "section_path": "Réunion/Suite",
            },
            instance=todo,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        todo.refresh_from_db()
        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Réunion", "Suite"])


class PathDisplayTests(PathTestCase):
    def test_detail_affiche_le_chemin(self):
        todo = self.save(section_path="Réunion/Préparation")

        html = self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()

        self.assertIn("<dt", html)
        self.assertRegex(html, r"<dt[^>]*>Chemin</dt>\s*<dd>Réunion › Préparation</dd>")
        self.assertNotIn(">Sujet<", html)

    def test_detail_sans_chemin(self):
        todo = self.save(section_path="")

        html = self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()

        self.assertRegex(html, r"<dt[^>]*>Chemin</dt>\s*<dd>Aucun</dd>")

    def test_formulaire_de_creation_a_le_champ_chemin(self):
        html = self.client.get(reverse("todolist:todo_create")).content.decode()

        self.assertIn(">Chemin", html)
        self.assertIn('name="section_path"', html)
        self.assertIn("<datalist", html)

    def test_creation_par_la_vue(self):
        response = self.client.post(
            reverse("todolist:todo_create"), self.data(section_path="Réunion/Suite")
        )

        self.assertRedirects(response, reverse("todolist:todo_list"))
        todo = Todo.objects.get()
        assert todo.section is not None
        self.assertEqual(levels(todo.section), ["Réunion", "Suite"])


class ListFilterTests(PathTestCase):
    def setUp(self):
        super().setUp()
        self.reunion = section_for(self.project, ["Réunion"])
        self.prep = section_for(self.project, ["Réunion", "Préparation"])
        self.autre = section_for(self.project, ["Autre"])
        make = Todo.objects.create
        self.a = make(
            title="Racine réunion", project=self.project, section=self.reunion
        )
        self.b = make(
            title="Dans la préparation", project=self.project, section=self.prep
        )
        self.c = make(title="Ailleurs", project=self.project, section=self.autre)
        self.d = make(title="Sans chemin", project=self.project)

    def titles(self, **params) -> list[str]:
        response = self.client.get(reverse("todolist:todo_list"), params)
        html = response.content.decode()
        return [
            title
            for title in (
                "Racine réunion",
                "Dans la préparation",
                "Ailleurs",
                "Sans chemin",
            )
            if f">{title}</a>" in html
        ]

    def test_sans_filtre_tout_est_la(self):
        self.assertEqual(len(self.titles()), 4)

    def test_un_niveau_inclut_ses_descendants(self):
        self.assertEqual(
            sorted(self.titles(path=self.reunion.pk)),
            ["Dans la préparation", "Racine réunion"],
        )

    def test_un_sous_niveau_n_inclut_pas_son_parent(self):
        self.assertEqual(self.titles(path=self.prep.pk), ["Dans la préparation"])

    def test_chemin_inconnu_ou_invalide_ignore(self):
        self.assertEqual(len(self.titles(path=99999)), 4)
        self.assertEqual(len(self.titles(path="abc")), 4)

    def test_parents_gardes_pour_le_contexte_et_attenues(self):
        Todo.objects.filter(pk=self.b.pk).update(parent=self.c)

        response = self.client.get(
            reverse("todolist:todo_list"), {"path": self.prep.pk}
        )
        html = response.content.decode()

        self.assertIn(">Ailleurs</a>", html)
        self.assertIn(">Dans la préparation</a>", html)
        # Le parent hors du chemin est attenué.
        row = html[html.index(f'data-task-id="{self.c.pk}"') :].split("</tr>")[0]
        self.assertIn("text-slate-500", row)
        child = html[html.index(f'data-task-id="{self.b.pk}"') :].split("</tr>")[0]
        self.assertNotIn("text-slate-500", child)

    def test_filtre_dans_le_panneau_de_la_colonne_tache(self):
        response = self.client.get(
            reverse("todolist:todo_list"), {"path": self.prep.pk}
        )
        html = response.content.decode()

        # Le chemin est un filtre de l'en-tête « Tâche » (#178), choisi parmi les chemins.
        self.assertRegex(
            html,
            rf'<input type="checkbox" id="path-{self.prep.pk}" name="path" '
            rf'value="{self.prep.pk}" checked>\s*<label[^>]*>Préparation</label>',
        )
        self.assertIn("Chemin : P › Réunion › Préparation", html)

    def test_pas_de_chip_sans_filtre(self):
        html = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertNotIn("Filtres actifs", html)
        self.assertIn('name="path"', html)

    def test_aucune_tache_pour_ce_niveau(self):
        empty = section_for(self.project, ["Vide"])

        response = self.client.get(reverse("todolist:todo_list"), {"path": empty.pk})

        self.assertContains(response, "Aucune tâche ne répond aux filtres.")
