"""La page d'une note affiche le texte tel qu'écrit ; les passages sont un index (#234)."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.services import process_passages

BODY = """Introduction avant tout titre.

# Beta

Texte de Beta.

## Suite

::: {.metadata}
tags: [m1]
:::

Texte de la suite.

# Alpha

Texte d'Alpha.
"""


class NotePageTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date="2025-11-24", body=BODY)
        process_passages(self.note)
        self.html = self.client.get(
            reverse("note_taking:note_detail", args=[self.note.date])
        ).content.decode()

    def test_texte_dans_l_ordre_ecrit(self):
        positions = [
            self.html.index(text)
            for text in (
                "Introduction avant tout titre.",
                "Texte de Beta.",
                "Texte de la suite.",
                "Texte d&#x27;Alpha." if "&#x27;" in self.html else "Texte d'Alpha.",
            )
        ]

        self.assertEqual(positions, sorted(positions))

    def test_titres_du_texte_sous_le_titre_de_la_page(self):
        self.assertInHTML('<h2 id="beta">Beta</h2>', self.html)
        self.assertInHTML('<h3 id="suite">Suite</h3>', self.html)
        self.assertEqual(self.html.count("<h1"), 1)

    def test_tags_du_bloc_de_metadonnees_en_pastille(self):
        self.assertIn(">m1</li>", self.html)
        self.assertNotIn("{.metadata}", self.html)

    def test_actions_conservees(self):
        for name in ("export_note", "edit_note", "delete_note"):
            self.assertIn(
                reverse(f"note_taking:{name}", args=[self.note.date]), self.html
            )

    def test_en_tete_collant_et_plan_dessous(self):
        """Les actions restent visibles, et une ancre s'arrête sous l'en-tête (#421)."""
        main = self.html[self.html.index('<main id="contenu"') :]

        self.assertIn("scroll-pt-18", main[: main.index(">")])
        header = main[main.index("<header") : main.index("</header>")]
        self.assertIn("sticky", header[: header.index(">")])
        self.assertIn(reverse("note_taking:edit_note", args=[self.note.date]), header)
        self.assertIn("truncate", header[header.index("<h1") : header.index("</h1>")])

    def test_feuille(self):
        self.assertRegex(
            self.html, r'<div class="rendered-content [^"]*\bbg-white\b[^"]*"'
        )
        # La page ne défile pas de côté : les contenus larges défilent seuls.
        css_path = finders.find("note_taking/style.css")
        assert isinstance(css_path, str)
        self.assertIn(
            ".rendered-content :is(pre, .table-scroll, .katex-display) {\n"
            "    overflow-x: auto;",
            Path(css_path).read_text(encoding="utf-8"),
        )
        # La même largeur avec et sans plan, que `note_reading.js` affiche ou masque.
        path = finders.find("note_taking/note_reading.js")
        assert isinstance(path, str)
        script = Path(path).read_text(encoding="utf-8")
        columns = "lg:grid-cols-[minmax(0,240mm)_16rem]"
        self.assertIn(columns, self.html)
        self.assertIn(f'"{columns}"', script)

    def test_autres_pages_sans_fond_de_feuille(self):
        html = self.client.get(reverse("note_taking:notes_list")).content.decode()
        main = html[html.index('<main id="contenu"') :]

        self.assertNotIn("bg-slate-100", main[: main.index(">")])

    def test_feuille_a_l_echelle(self):
        """Quand la place manque, la feuille rétrécit en entier (#421)."""
        self.assertIn("data-note-frame", self.html)
        self.assertIn("[zoom:var(--note-zoom,1)]", self.html)
        self.assertIn("note_taking/note_sheet.js", self.html)
        # Sans place réservée, la barre de défilement changerait l'échelle, qui la
        # ferait disparaître, et ainsi de suite.
        self.assertIn("[scrollbar-gutter:stable]", self.html)
        # La largeur du script est celle de la colonne du gabarit.
        path = finders.find("note_taking/note_sheet.js")
        assert isinstance(path, str)
        self.assertIn("(240 * 96) / 25.4", Path(path).read_text(encoding="utf-8"))
        self.assertIn("minmax(0,240mm)", self.html)
