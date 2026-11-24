"""La fiche d'un projet : ses blocs, déclarés par les apps, et son arbre de chemins qui
les restreint à un niveau (#205)."""

import re
from datetime import date

from django.db import connection
from django.template import Context, Template
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Project, Section
from core.sections import section_for
from images.models import Image
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


class ProjectPageTestCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="P", description="Un projet.")
        self.other = Project.objects.create(name="Q")

    def note(self, body: str, day: str = "2025-11-24") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def section(self, *names: str) -> Section:
        section = section_for(self.project, names)
        assert section is not None
        return section

    def task(self, title: str, **fields) -> Task:
        return Task.objects.create(title=title, project=self.project, **fields)

    def url(self) -> str:
        return f"/projects/{self.project.pk}/"

    def get(self, **params) -> str:
        response = self.client.get(self.url(), params)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def block(self, key: str, **params) -> str:
        """Le HTML d'un bloc de la fiche, jusqu'au bloc suivant."""
        html = self.get(**params)
        found = re.search(
            rf'<section id="{key}".*?(?=<section id="|</main>)', html, re.S
        )
        self.assertIsNotNone(found, f"bloc {key} absent")
        assert found is not None
        return found[0]


class PageTests(ProjectPageTestCase):
    def test_titre_description_et_actions(self):
        html = self.get()

        self.assertRegex(html, r"<title>\s*Projet « P »")
        self.assertIn("Un projet.", html)
        for name in ("core:project_paths", "core:project_edit"):
            self.assertIn(f'href="{reverse(name, args=[self.project.pk])}"', html)

    def test_projet_inconnu(self):
        self.assertEqual(self.client.get("/projects/999/").status_code, 404)

    def test_blocs_dans_l_ordre_avec_un_sommaire(self):
        self.note("# P\nx")
        self.task("T")

        html = self.get()

        keys = ["project-tasks", "project-notes", "project-timeline"]
        self.assertEqual(re.findall(r'<section id="([\w-]+)"', html), keys)
        self.assertEqual(re.findall(r'href="#(project-[\w-]+)"', html), keys)

    def test_projet_vide(self):
        html = self.get()

        self.assertIn("Aucune tâche en cours.", html)
        self.assertIn("Aucun passage.", html)
        self.assertNotIn("project-images", html)
        self.assertNotIn("project-timeline", html)

    def test_nombre_de_requetes_constant(self):
        def count() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.get()
            return len(captured)

        self.note("# P\n## A\nx\n- [ ] Une")
        before = count()
        for day in range(1, 8):
            self.note(f"# P\n## A{day}\n### B\nx\n- [ ] Une", f"2025-12-0{day}")

        self.assertEqual(count(), before)


class PathFilterTests(ProjectPageTestCase):
    def setUp(self):
        super().setUp()
        self.note(
            "# P\n## A\nTexte de A\n- [ ] Une\n### B\nTexte de B\n## C\nTexte de C"
        )
        self.task("Main", section=self.section("C"))

    def test_arbre_du_projet_en_liens(self):
        section = self.section("A")

        html = self.get()

        self.assertRegex(html, rf'href="{self.url()}\?path={section.pk}"[^>]*>A</a>')

    def test_un_niveau_et_ses_descendants(self):
        html = self.get(path=self.section("A").pk)

        self.assertIn("Texte de A", html)
        self.assertIn("Texte de B", html)
        self.assertNotIn("Texte de C", html)
        self.assertIn(">Une</a>", html)
        self.assertNotIn(">Main</a>", html)

    def test_niveau_choisi_nomme_et_retirable(self):
        html = self.get(path=self.section("A", "B").pk)

        self.assertIn("A › B", html)
        self.assertIn(f'href="{self.url()}">Tout le projet</a>', html)

    def test_retirer_le_niveau_garde_le_reste(self):
        html = self.get(path=self.section("A").pk, state="all")

        self.assertIn(f'href="{self.url()}?state=all">Tout le projet</a>', html)

    def test_niveau_inconnu_invalide_ou_d_un_autre_projet_ignore(self):
        elsewhere = section_for(self.other, ["A"])
        assert elsewhere is not None

        for value in ("99999", "abc", "²", str(elsewhere.pk)):
            with self.subTest(value=value):
                self.assertIn("Texte de C", self.get(path=value))


class TasksBlockTests(ProjectPageTestCase):
    KEY = "project-tasks"

    def test_taches_du_projet_seulement(self):
        self.task("Ici")
        Task.objects.create(title="Ailleurs", project=self.other)

        block = self.block(self.KEY)

        self.assertIn(">Ici</a>", block)
        self.assertNotIn("Ailleurs", block)

    def test_en_cours_par_defaut_puis_terminees_ou_toutes(self):
        self.task("Ouverte")
        self.task("Finie", progress=100)

        def titles(**params) -> list[str]:
            block = self.block(self.KEY, **params)
            return [t for t in ("Ouverte", "Finie") if f">{t}</a>" in block]

        self.assertEqual(titles(), ["Ouverte"])
        self.assertEqual(titles(state="done"), ["Finie"])
        self.assertEqual(titles(state="all"), ["Ouverte", "Finie"])
        # Les écartées ont leur tableau dans la liste des tâches.
        self.assertEqual(titles(state="dismissed"), ["Ouverte"])

    def test_cases_a_cocher_utilisables(self):
        """Le cookie que lit `task.js` est posé, sans autre page visitée avant."""
        self.task("T")

        block = self.block(self.KEY)

        self.assertIn("todolist/task.js", block)
        self.assertIn("csrftoken", self.client.cookies)

    def test_parent_d_un_autre_projet_attenue(self):
        parent = Task.objects.create(title="Parent", project=self.other)
        self.task("Enfant", parent=parent)

        block = self.block(self.KEY)

        row = block[block.index(f'data-task-id="{parent.pk}"') :].split("</tr>")[0]
        self.assertIn("text-slate-500", row)
        self.assertIn(">Enfant</a>", block)

    def test_lien_vers_la_liste_filtree(self):
        section = self.section("A")
        url = reverse("todolist:task_list")

        self.assertIn(f'href="{url}?project=P"', self.block(self.KEY))
        self.assertIn(
            f'href="{url}?path={section.pk}&amp;state=all"',
            self.block(self.KEY, path=section.pk, state="all"),
        )


class TimelineBlockTests(ProjectPageTestCase):
    def test_frise_des_memes_taches(self):
        parent = self.task("Parent", due_date=date(2026, 12, 1))
        self.task("Enfant", parent=parent)
        self.task("Finie", progress=100)

        block = self.block("project-timeline")

        self.assertEqual(
            re.findall(r"data-gantt-row[^>]*>\s*<a[^>]*>(.*?)</a>", block),
            ["Parent", "Enfant"],
        )
        self.assertNotIn("Échéance de la tâche", block)


class NotesBlockTests(ProjectPageTestCase):
    KEY = "project-notes"

    def setUp(self):
        super().setUp()
        self.note("# P\nDirect\n## A\nPremier\n# Q\nAilleurs", "2025-11-24")
        self.note("# P\n## A\nSecond\n## A\nEncore", "2025-11-25")

    def excerpts(self, **params) -> list[str]:
        block = self.block(self.KEY, **params)
        return re.findall(r"\b(?:Direct|Premier|Second|Encore|Ailleurs)\b", block)

    def test_par_note_les_recentes_d_abord(self):
        self.assertEqual(self.excerpts(), ["Second", "Encore", "Direct", "Premier"])

    def test_par_note_les_anciennes_d_abord(self):
        self.assertEqual(
            self.excerpts(order="asc"), ["Direct", "Premier", "Second", "Encore"]
        )

    def test_par_chemin(self):
        self.assertEqual(
            self.excerpts(group="path"), ["Direct", "Second", "Encore", "Premier"]
        )
        self.assertEqual(
            self.excerpts(group="path", order="asc"),
            ["Direct", "Premier", "Second", "Encore"],
        )

    def test_regroupement_inconnu_ignore(self):
        self.assertEqual(len(self.excerpts(group="x", order="y")), 4)

    def test_chaque_passage_mene_a_son_titre(self):
        """À sa propre occurrence d'un titre répété."""
        block = self.block(self.KEY)

        url = reverse("note_taking:note_detail", args=["2025-11-25"])
        self.assertIn(f'href="{url}#a"', block)
        self.assertIn(f'href="{url}#a-1"', block)

    def test_lien_vers_le_document(self):
        section = self.section("A")
        url = reverse("note_taking:notes_search")

        self.assertIn(
            f'href="{url}?projects={self.project.pk}&amp;view=document&amp;group=date"',
            self.block(self.KEY),
        )
        self.assertIn(
            f'href="{url}?subjects={section.pk}&amp;view=document&amp;group=path"',
            self.block(self.KEY, path=section.pk, group="path"),
        )

    def test_le_lien_du_document_montre_les_memes_passages(self):
        found = re.search(r'href="([^"]*view=document[^"]*)"', self.block(self.KEY))
        assert found is not None

        response = self.client.get(found[1].replace("&amp;", "&"))

        self.assertContains(response, "4 passages dans 2 notes")

    def test_les_options_gardent_le_niveau_et_l_etat(self):
        section = self.section("A")

        block = self.block(self.KEY, path=section.pk, state="all")

        self.assertIn(
            f'href="?path={section.pk}&amp;state=all&amp;group=path#{self.KEY}"', block
        )

    def test_extrait_echappe(self):
        self.note("# P\nUn <b>texte</b>", "2025-11-26")

        self.assertIn("Un &lt;b&gt;texte&lt;/b&gt;", self.block(self.KEY))


class ImagesBlockTests(ProjectPageTestCase):
    KEY = "project-images"

    def setUp(self):
        super().setUp()
        for name in ("a.png", "b.png"):
            Image.objects.create(name=name, file=f"note_images/{name}")

    def names(self, **params) -> list[str]:
        block = self.block(self.KEY, **params)
        return re.findall(r">([ab]\.png)</figcaption>", block)

    def test_images_utilisees_une_fois_chacune(self):
        self.note(
            "# P\n## A\n![](images/a.png)\n## C\n![](images/a.png)\n"
            "# Q\n![](images/b.png)"
        )

        self.assertEqual(self.names(), ["a.png"])

    def test_images_du_niveau_choisi(self):
        self.note("# P\n## A\n![](images/a.png)\n## C\n![](images/b.png)")

        self.assertEqual(self.names(path=self.section("C").pk), ["b.png"])


class LinksTests(ProjectPageTestCase):
    """La fiche s'ouvre depuis les pastilles de projet."""

    def test_pastille_en_lien(self):
        html = Template("{% load ui %}{% project_badge p link=True %}").render(
            Context({"p": self.project})
        )

        self.assertInHTML(f'<a href="{self.url()}">P</a>', html)

    def test_pastille_seule_par_defaut(self):
        html = Template("{% load ui %}{% project_badge p %}").render(
            Context({"p": self.project})
        )

        self.assertNotIn("<a", html)

    def test_depuis_les_pages(self):
        note = self.note("# P\n## A\nx")
        task = self.task("T", section=self.section("A"))
        pages = {
            "projets": reverse("core:projects"),
            "chemins": reverse("core:project_paths", args=[self.project.pk]),
            "liste des tâches": reverse("todolist:task_list"),
            "tâche": reverse("todolist:task_detail", args=[task.pk]),
            "liste des notes": reverse("note_taking:notes_list"),
            "note": reverse("note_taking:note_detail", args=[note.date]),
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                self.assertContains(self.client.get(url), f'href="{self.url()}"')
