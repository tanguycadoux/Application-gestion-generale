"""Choix de la tâche parente (#390) : les tâches les plus proches d'abord (même
chemin, même projet, autres projets), en cours par défaut, sans la tâche ni ses
descendantes, titres longs tronqués ; la liste suit le projet et le chemin."""

from datetime import date
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from core.sections import section_for
from todolist.models import Todo


class ParentSelectParser(HTMLParser):
    """Le `<select name="parent">` d'une page : ses groupes et leurs options."""

    def __init__(self):
        super().__init__()
        self.in_select = False
        self.group: str | None = None
        self.option: dict | None = None
        self.options: list[dict] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select" and attributes.get("name") == "parent":
            self.in_select = True
        elif self.in_select and tag == "optgroup":
            self.group = attributes.get("label")
        elif self.in_select and tag == "option":
            self.option = {
                "value": attributes.get("value"),
                "title": attributes.get("title"),
                "selected": "selected" in attributes,
                "group": self.group,
                "text": "",
            }

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_select = False
        elif tag == "optgroup":
            self.group = None
        elif tag == "option" and self.option is not None:
            self.option["text"] = self.option["text"].strip()
            self.options.append(self.option)
            self.option = None

    def handle_data(self, data):
        if self.option is not None:
            self.option["text"] += data


def parent_options(html: str) -> list[dict]:
    parser = ParentSelectParser()
    parser.feed(html)
    return [option for option in parser.options if option["value"]]


class ParentChoiceTestCase(TestCase):
    def setUp(self):
        self.p = Project.objects.create(name="P")
        self.q = Project.objects.create(name="Q")
        self.reunion = section_for(self.p, ["Réunion"])
        self.bilan = section_for(self.p, ["Bilan"])
        self.todo = Todo.objects.create(
            title="Tâche", project=self.p, section=self.reunion
        )

    def task(self, title: str, project=None, section=None, **fields) -> Todo:
        return Todo.objects.create(
            title=title, project=project or self.p, section=section, **fields
        )

    def edit_options(self, todo=None) -> list[dict]:
        todo = todo or self.todo
        html = self.client.get(reverse("todolist:todo_edit", args=[todo.pk]))
        return parent_options(html.content.decode())

    def texts(self, options) -> list[str]:
        return [option["text"] for option in options]


class GroupsTests(ParentChoiceTestCase):
    def test_meme_chemin_puis_meme_projet_puis_autres_projets(self):
        self.task("Ailleurs", project=self.q)
        self.task("Bilan annuel", section=self.bilan)
        self.task("Ordre du jour", section=self.reunion)

        options = self.edit_options()

        self.assertEqual(
            [(option["group"], option["text"]) for option in options],
            [
                ("Même chemin", "Ordre du jour"),
                ("Même projet", "Bilan › Bilan annuel"),
                ("Autres projets", "Q › Ailleurs"),
            ],
        )

    def test_tache_sans_chemin_meme_chemin_est_la_racine_du_projet(self):
        todo = self.task("Sans chemin")
        self.task("Racine")
        self.task("Ordre du jour", section=self.reunion)

        options = self.edit_options(todo)

        self.assertEqual(
            [(option["group"], option["text"]) for option in options],
            [
                ("Même chemin", "Racine"),
                ("Même projet", "Réunion › Ordre du jour"),
                ("Même projet", "Réunion › Tâche"),
            ],
        )

    def test_par_echeance_puis_titre_sans_echeance_a_la_fin(self):
        self.task("C", section=self.reunion)
        self.task("B", section=self.reunion, due_date=date(2026, 12, 1))
        self.task("A", section=self.reunion, due_date=date(2026, 11, 20))
        self.task("D", section=self.reunion)

        options = self.edit_options()

        self.assertEqual(self.texts(options), ["A", "B", "C", "D"])

    def test_groupe_vide_absent(self):
        self.task("Ordre du jour", section=self.reunion)

        html = self.client.get(
            reverse("todolist:todo_edit", args=[self.todo.pk])
        ).content.decode()

        self.assertIn('label="Même chemin"', html)
        self.assertNotIn('label="Même projet"', html)
        self.assertNotIn('label="Autres projets"', html)


class ExcludedTasksTests(ParentChoiceTestCase):
    def test_ni_la_tache_ni_ses_descendantes(self):
        child = self.task("Enfant", section=self.reunion, parent=self.todo)
        self.task("Petit-enfant", section=self.reunion, parent=child)
        self.task("Voisine", section=self.reunion)

        options = self.edit_options()

        self.assertEqual(self.texts(options), ["Voisine"])

    def test_terminees_masquees_par_defaut(self):
        self.task("Finie", section=self.reunion, progress=100)
        self.task("En cours", section=self.reunion)

        options = self.edit_options()

        self.assertEqual(self.texts(options), ["En cours"])

    def test_parent_actuel_garde_meme_termine(self):
        parent = self.task("Parent fini", section=self.reunion)
        self.todo.parent = parent
        self.todo.save()
        Todo.objects.filter(pk=parent.pk).update(done=True, progress=100)

        options = self.edit_options()

        self.assertEqual(self.texts(options), ["Parent fini"])
        self.assertTrue(options[0]["selected"])

    def test_tache_ecartee_absente(self):
        self.task(
            "Écartée",
            section=self.reunion,
            created_from_note=True,
            note_state=Todo.NoteState.DISMISSED,
        )

        self.assertEqual(self.edit_options(), [])


class LabelsTests(ParentChoiceTestCase):
    def test_titre_long_tronque_titre_complet_en_infobulle(self):
        long_title = "Relire " + "très " * 40 + "longuement"
        self.task(long_title, section=self.reunion)

        (option,) = self.edit_options()

        self.assertLessEqual(len(option["text"]), 81)
        self.assertTrue(option["text"].endswith("…"))
        self.assertEqual(option["title"], long_title)

    def test_titre_court_sans_infobulle(self):
        self.task("Court", section=self.reunion)

        (option,) = self.edit_options()

        self.assertIsNone(option["title"])


class ChoicesEndpointTests(ParentChoiceTestCase):
    """La liste rechargée quand le projet, le chemin ou la case changent."""

    def get(self, **params):
        url = reverse("todolist:parent_choices")
        return self.client.get(url, {"todo": self.todo.pk, **params})

    def test_suit_le_projet_et_le_chemin_saisis(self):
        self.task("Bilan annuel", section=self.bilan)
        self.task("Ailleurs", project=self.q)

        response = self.get(project=self.p.pk, section_path="bilan")

        options = parent_options(response.content.decode())
        self.assertEqual(
            [(option["group"], option["text"]) for option in options],
            [
                ("Même chemin", "Bilan annuel"),
                ("Autres projets", "Q › Ailleurs"),
            ],
        )

    def test_autre_projet_choisi(self):
        self.task("Ailleurs", project=self.q)
        self.task("Ordre du jour", section=self.reunion)

        response = self.get(project=self.q.pk, section_path="")

        options = parent_options(response.content.decode())
        self.assertEqual(
            [(option["group"], option["text"]) for option in options],
            [
                ("Même chemin", "Ailleurs"),
                ("Autres projets", "P › Réunion › Ordre du jour"),
            ],
        )

    def test_case_des_terminees(self):
        self.task("Finie", section=self.reunion, progress=100)

        hidden = parent_options(self.get(project=self.p.pk).content.decode())
        shown = parent_options(
            self.get(project=self.p.pk, parent_show_done="1").content.decode()
        )

        self.assertEqual(hidden, [])
        self.assertEqual(self.texts(shown), ["Réunion › Finie"])

    def test_parent_choisi_reste_choisi(self):
        parent = self.task("Ordre du jour", section=self.reunion)

        response = self.get(project=self.q.pk, parent=parent.pk)

        options = parent_options(response.content.decode())
        self.assertEqual([option["selected"] for option in options], [True])

    def test_nouvelle_tache_sans_projet(self):
        self.task("Ordre du jour", section=self.reunion)
        url = reverse("todolist:parent_choices")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.texts(parent_options(response.content.decode())),
            ["P › Réunion › Ordre du jour", "P › Réunion › Tâche"],
        )

    def test_seulement_le_champ(self):
        html = self.get(project=self.p.pk).content.decode()

        self.assertNotIn("<html", html)
        self.assertIn('name="parent"', html)
        self.assertIn('name="parent_show_done"', html)


class FormTests(ParentChoiceTestCase):
    def test_champ_recharge_par_htmx(self):
        html = self.client.get(
            reverse("todolist:todo_edit", args=[self.todo.pk])
        ).content.decode()

        url = reverse("todolist:parent_choices")
        self.assertIn(f'data-hx-get="{url}?todo={self.todo.pk}"', html)
        self.assertIn('name="parent_show_done"', html)

    def test_parent_d_un_autre_projet_permis(self):
        """L'écart de projet reste signalé, pas empêché (#165)."""
        other = self.task("Ailleurs", project=self.q)

        response = self.client.post(
            reverse("todolist:todo_edit", args=[self.todo.pk]),
            {
                "title": "Tâche",
                "priority": "medium",
                "progress": 0,
                "project": self.p.pk,
                "section_path": "Réunion",
                "parent": other.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.parent, other)

    def test_creation_d_une_sous_tache(self):
        """`?parent=` : le parent est choisi, son projet aussi."""
        parent = self.task("Ordre du jour", section=self.reunion)

        html = self.client.get(
            reverse("todolist:todo_create") + f"?parent={parent.pk}"
        ).content.decode()

        selected = [o for o in parent_options(html) if o["selected"]]
        self.assertEqual(self.texts(selected), ["Réunion › Ordre du jour"])

    def test_formulaire_refuse_garde_la_case(self):
        response = self.client.post(
            reverse("todolist:todo_edit", args=[self.todo.pk]),
            {
                "title": "",
                "priority": "medium",
                "progress": 0,
                "project": self.p.pk,
                "parent_show_done": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode(), r'<input[^>]*name="parent_show_done"[^>]*checked'
        )
