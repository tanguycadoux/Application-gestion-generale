"""Tests des dates : trois formats d'affichage communs, toujours en <time> (#129)."""

import datetime
import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from todolist.models import Todo

APPS = ("core", "images", "note_taking", "todolist")

# Formats techniques, qui ne s'affichent pas comme une date : attributs datetime,
# paramètres d'URL, valeur d'un champ date, mois du calendrier.
TECHNICAL_FORMATS = {"Y-m-d", "c", "Y-m", "F Y"}

DATE_FILTER_REGEX = re.compile(r"\|date:['\"](?P<format>[^'\"]*)['\"]")


def render(source: str, **context) -> str:
    return Template("{% load ui %}" + source).render(Context(context))


class DateFormatsTests(SimpleTestCase):
    def test_trois_formats(self):
        day = datetime.date(2025, 11, 24)

        self.assertEqual(
            render('{{ d|date_text:"long" }}', d=day), "lundi 24 novembre 2025"
        )
        self.assertEqual(render('{{ d|date_text:"moyen" }}', d=day), "24 novembre 2025")
        self.assertEqual(
            render('{{ d|date_text:"court" }}', d=day), "lun. 24 nov. 2025"
        )

    def test_mois_abreges_en_francais(self):
        """Le code M de Django abrège juin et juillet en « Jui » : le format court
        utilise N, aux abréviations françaises."""
        self.assertEqual(
            render('{{ d|date_text:"court" }}', d=datetime.date(2026, 7, 14)),
            "mar. 14 juil. 2026",
        )
        self.assertEqual(
            render('{{ d|date_text:"court" }}', d=datetime.date(2026, 6, 7)),
            "dim. 7 juin 2026",
        )

    def test_balise_time(self):
        html = render('{% date_time d "long" %}', d=datetime.date(2025, 11, 24))

        self.assertHTMLEqual(
            html, '<time datetime="2025-11-24">lundi 24 novembre 2025</time>'
        )

    def test_date_et_heure_dans_le_fuseau_de_l_application(self):
        moment = datetime.datetime(2025, 11, 24, 23, 30, tzinfo=datetime.UTC)

        html = render('{% date_time d "moyen" %}', d=moment)

        self.assertHTMLEqual(
            html,
            '<time datetime="2025-11-25T00:30:00+01:00">25 novembre 2025</time>',
        )

    def test_heure_a_la_seconde(self):
        """Le format de datetime n'admet que trois décimales au plus (#259)."""
        moment = datetime.datetime(2025, 11, 24, 10, 0, 5, 985044, tzinfo=datetime.UTC)

        html = render('{% date_time d "moyen" %}', d=moment)

        self.assertIn('datetime="2025-11-24T11:00:05+01:00"', html)

    def test_format_inconnu_refuse(self):
        with self.assertRaises(ValueError):
            render('{{ d|date_text:"autre" }}', d=datetime.date(2025, 11, 24))

    def test_date_vide(self):
        self.assertEqual(render('{% date_time d "long" %}', d=None).strip(), "")


class DatesInTemplatesTests(SimpleTestCase):
    def test_pas_de_format_d_affichage_propre_aux_gabarits(self):
        for app in APPS:
            for path in (Path(settings.BASE_DIR) / app).glob("**/templates/**/*.html"):
                formats = set(
                    DATE_FILTER_REGEX.findall(path.read_text(encoding="utf-8"))
                )
                with self.subTest(path=path.name):
                    self.assertLessEqual(formats, TECHNICAL_FORMATS)


class DatesInPagesTests(TestCase):
    LONG = '<time datetime="2025-11-24">lundi 24 novembre 2025</time>'

    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body="# P\nx")
        self.project = Project.objects.create(name="P")
        NotePart.objects.create(note=self.note, project=self.project, content="x")

    def test_titre_d_une_note(self):
        html = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.pk])
        ).content.decode()

        self.assertInHTML(f"<h1 class='flex-1'>Note du {self.LONG}</h1>", html)
        self.assertIn('data-confirm="Supprimer définitivement la note du 24', html)

    def test_vue_markdown(self):
        html = self.client.get(
            reverse("note_taking:note_md", args=[self.note.pk])
        ).content.decode()

        self.assertIn(
            "<title>Note du 24 novembre 2025 en Markdown · Notes</title>", html
        )
        self.assertInHTML(f"<h1>Note du {self.LONG}</h1>", html)

    def test_tableau_des_notes_en_format_court(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()

        self.assertInHTML(
            '<time datetime="2025-11-24">lun. 24 nov. 2025</time>', html, count=1
        )

    def test_resultats_de_recherche(self):
        html = self.client.post(
            reverse("note_taking:notes_search"), {"projects": [self.project.pk]}
        ).content.decode()

        self.assertIn(f"Note du {self.LONG}", html)

    def test_echeance_d_une_todo(self):
        todo = Todo.objects.create(
            project=Project.objects.get_or_create(name="P")[0],
            title="T",
            due_date="2025-11-24",
        )

        detail = self.client.get(
            reverse("todolist:todo_detail", args=[todo.pk])
        ).content.decode()
        listing = self.client.get(reverse("todolist:todo_list")).content.decode()

        self.assertInHTML('<time datetime="2025-11-24">24 novembre 2025</time>', detail)
        self.assertInHTML(
            '<time datetime="2025-11-24">lun. 24 nov. 2025</time>', listing
        )
