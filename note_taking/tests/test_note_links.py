"""Liens entre notes, compatibles Quarto (#206) : `[texte](AAAA-MM-JJ.qmd#ancre)`."""

from datetime import date

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.qmd.export import note_to_qmd
from note_taking.qmd.links import NoteLink, from_quarto, note_links, to_quarto
from note_taking.rendering import render_note_body
from note_taking.services import (
    insert_note_in_table,
    process_passages,
    update_note_from_source_file,
)
from note_taking.tests.links import new_tab_link


class NoteLinksParsingTests(SimpleTestCase):
    """Les liens d'un texte vers d'autres notes, sans accès à la base."""

    def test_lien_simple(self):
        self.assertEqual(
            note_links("Voir [la veille](2026-03-12.qmd)."),
            [NoteLink(date(2026, 3, 12), "")],
        )

    def test_lien_avec_ancre(self):
        self.assertEqual(
            note_links("[réunion](2026-03-12.qmd#reunion-1)"),
            [NoteLink(date(2026, 3, 12), "reunion-1")],
        )

    def test_lien_avec_titre(self):
        self.assertEqual(
            note_links('[x](2026-03-12.qmd "La veille")'),
            [NoteLink(date(2026, 3, 12), "")],
        )

    def test_dans_l_ordre_sans_doublon(self):
        self.assertEqual(
            note_links(
                "[a](2026-03-12.qmd) [b](2026-01-02.qmd)\n[c](2026-03-12.qmd)\n"
                "[d](2026-03-12.qmd#suite)"
            ),
            [
                NoteLink(date(2026, 3, 12), ""),
                NoteLink(date(2026, 1, 2), ""),
                NoteLink(date(2026, 3, 12), "suite"),
            ],
        )

    def test_ni_image_ni_autre_fichier_ni_adresse(self):
        self.assertEqual(
            note_links(
                "![](2026-03-12.qmd) [a](notes/2026-03-12.qmd) [b](2026-03-12.html) "
                "[c](https://exemple.fr/2026-03-12.qmd) [d](2026-3-12.qmd)"
            ),
            [],
        )

    def test_date_invalide_ignoree(self):
        self.assertEqual(note_links("[a](2026-13-45.qmd)"), [])

    def test_pas_dans_le_code(self):
        self.assertEqual(
            note_links(
                "`[a](2026-03-12.qmd)`\n```\n[b](2026-03-13.qmd)\n```\n"
                "~~~\n[c](2026-03-14.qmd)\n~~~\n[d](2026-03-15.qmd)"
            ),
            [NoteLink(date(2026, 3, 15), "")],
        )


class NoteLinksRenderingTests(TestCase):
    def setUp(self):
        Note.objects.create(date="2026-03-12", body="# P\n## Réunion\nx")

    def test_lien_vers_la_page_de_la_note(self):
        html = render_note_body("[la veille](2026-03-12.qmd)")

        url = reverse("note_taking:note_detail", args=["2026-03-12"])
        self.assertIn(new_tab_link(url, "la veille"), html)

    def test_lien_vers_la_section(self):
        html = render_note_body("[réunion](2026-03-12.qmd#reunion)")

        url = reverse("note_taking:note_detail", args=["2026-03-12"])
        self.assertIn(new_tab_link(f"{url}#reunion", "réunion"), html)

    def test_dans_un_passage(self):
        from note_taking.rendering import render_passage

        html = render_passage("[la veille](2026-03-12.qmd)")

        self.assertIn(
            f'href="{reverse("note_taking:note_detail", args=["2026-03-12"])}"', html
        )

    def test_note_absente_signalee(self):
        html = render_note_body('[demain](2026-03-13.qmd#suite "Le lendemain")')

        self.assertIn("note-link-missing", html)
        self.assertIn("Aucune note le 13 mars 2026", html)
        # Le lien mène à la création de la note, à sa date.
        self.assertIn(f'href="{reverse("note_taking:new_note")}?date=2026-03-13"', html)
        # Un seul titre : l'explication remplace celui écrit.
        self.assertEqual(html.count("title="), 1)
        self.assertIn(">demain<", html)
        self.assertIn('target="_blank"', html)

    def test_autres_liens_inchanges(self):
        html = render_note_body("[a](https://exemple.fr) [b](autre.qmd)")

        self.assertIn('href="https://exemple.fr"', html)
        self.assertIn('href="autre.qmd"', html)
        self.assertNotIn("note-link-missing", html)

    def test_lien_dans_le_code_inchange(self):
        html = render_note_body("`[a](2026-03-13.qmd)`")

        self.assertNotIn("note-link-missing", html)
        self.assertNotIn("<a ", html)

    def test_page_de_la_note(self):
        note = Note.objects.create(date="2026-03-14", body="# P\n[v](2026-03-12.qmd)")
        process_passages(note)

        response = self.client.get(reverse("note_taking:note_detail", args=[note.date]))

        self.assertContains(
            response,
            f'href="{reverse("note_taking:note_detail", args=["2026-03-12"])}"',
        )


class NoteLinksExportTests(SimpleTestCase):
    def test_lien_avec_extension_garde_tel_quel(self):
        """L'export met les notes à la racine : le lien mène au fichier voisin, que
        Quarto transforme en lien vers sa page `.html`."""
        body = "# P\n[la veille](2026-03-12.qmd#reunion)"

        qmd = note_to_qmd(Note(date="2026-03-13", body=body))

        self.assertTrue(qmd.endswith(body))

    def test_extension_ajoutee_a_l_export(self):
        """Écrit sans extension dans l'application, le lien devient le fichier de la
        note à l'export : Quarto ne suit que `AAAA-MM-JJ.qmd`."""
        body = '# P\n[la veille](2026-03-12#reunion "titre") et [x](2026-03-11)'

        qmd = note_to_qmd(Note(date="2026-03-13", body=body))

        self.assertTrue(
            qmd.endswith(
                '# P\n[la veille](2026-03-12.qmd#reunion "titre") et [x](2026-03-11.qmd)'
            )
        )


class QuartoLinkFormTests(SimpleTestCase):
    """Forme des liens : sans extension dans l'application, `.qmd` dans les fichiers."""

    def test_vers_quarto(self):
        self.assertEqual(
            to_quarto("[a](2026-03-12) [b](2026-03-12.qmd) [c](2026-03-12#x)"),
            "[a](2026-03-12.qmd) [b](2026-03-12.qmd) [c](2026-03-12.qmd#x)",
        )

    def test_depuis_quarto(self):
        self.assertEqual(
            from_quarto(
                '[a](2026-03-12.qmd) [b](2026-03-12) [c](2026-03-12.qmd#x "t")'
            ),
            '[a](2026-03-12) [b](2026-03-12) [c](2026-03-12#x "t")',
        )

    def test_code_et_images_inchanges(self):
        text = (
            "`[a](2026-03-12)` ![i](2026-03-12.png)\n"
            "```\n[b](2026-03-12)\n```\n"
            "[c](2026-03-12)"
        )

        self.assertEqual(
            to_quarto(text),
            text.replace("[c](2026-03-12)", "[c](2026-03-12.qmd)"),
        )

    def test_aller_retour(self):
        body = "[a](2026-03-12#x) `[b](2026-03-12)`"

        self.assertEqual(from_quarto(to_quarto(body)), body)


class NoteLinksImportTests(TestCase):
    def file(self, name, content):
        return SimpleUploadedFile(name, content.encode())

    def test_extension_retiree_a_l_import(self):
        note = insert_note_in_table(
            self.file(
                "2026-03-13.qmd", "---\ndate: 2026-03-13\n---\n\n[v](2026-03-12.qmd)"
            )
        )

        self.assertEqual(note.body, "[v](2026-03-12)")

    def test_export_puis_import_redonne_le_corps(self):
        body = "# P\n\n[la veille](2026-03-12#reunion)\n"
        qmd = note_to_qmd(Note(date="2026-03-13", body=body))

        note = insert_note_in_table(self.file("2026-03-13.qmd", qmd))

        self.assertEqual(note.body, body)

    def test_remplacement_du_fichier_source(self):
        note = Note.objects.create(date="2026-03-13", body="")

        update_note_from_source_file(
            note,
            self.file(
                "2026-03-13.qmd", "---\ndate: 2026-03-13\n---\n\n[v](2026-03-12.qmd#a)"
            ),
        )

        self.assertEqual(note.body, "[v](2026-03-12#a)")


class ExtensionlessLinkTests(TestCase):
    """`[texte](AAAA-MM-JJ)` : la forme écrite dans l'application."""

    def test_lu_comme_un_lien(self):
        self.assertEqual(
            note_links('Voir [la veille](2026-03-12#a "titre") et [x](2026-03-11).'),
            [NoteLink(date(2026, 3, 12), "a"), NoteLink(date(2026, 3, 11), "")],
        )

    def test_autres_suffixes_ignores(self):
        self.assertEqual(
            note_links("[a](2026-03-12.pdf) [b](2026-03-12-bis) [c](2026-03-12/x)"), []
        )

    def test_rendu_vers_la_page_de_la_note(self):
        Note.objects.create(date="2026-03-12", body="")

        html = render_note_body("[la veille](2026-03-12#reunion)")

        url = reverse("note_taking:note_detail", args=["2026-03-12"])
        self.assertIn(f'href="{url}#reunion"', html)

    def test_rendu_note_absente(self):
        html = render_note_body("[plus tard](2026-04-01)")

        self.assertIn("note-link-missing", html)


class NoteLinksWarningTests(TestCase):
    def test_avertissement_a_l_enregistrement(self):
        Note.objects.create(date="2026-03-12", body="")

        response = self.client.post(
            reverse("note_taking:new_note"),
            {
                "date": "2026-03-14",
                "body": "# P\n[a](2026-03-12.qmd) [b](2026-03-13.qmd) [c](2026-03-11.qmd)",
            },
        )

        texts = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "Liens vers des notes absentes (11 mars 2026, 13 mars 2026) : signalés "
            "dans la page, ils mèneront aux notes une fois créées.",
            texts,
        )

    def test_une_seule_note_absente(self):
        note = Note.objects.create(date="2026-03-14", body="# P\n[b](2026-03-13.qmd)")
        process_passages(note)

        self.assertEqual(note.missing_links, (date(2026, 3, 13),))

    def test_lien_vers_soi_meme_pas_absent(self):
        note = Note.objects.create(date="2026-03-14", body="# P\n[b](2026-03-14.qmd#p)")
        process_passages(note)

        self.assertEqual(note.missing_links, ())


class NoteSuggestionsTests(TestCase):
    """Les notes proposées par l'éditeur après `](` (#206)."""

    def results(self, **params) -> list[dict]:
        response = self.client.get(reverse("note_taking:note_suggestions"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_fichier_a_ecrire_et_date_en_texte(self):
        Note.objects.create(date="2026-03-12", body="")

        self.assertEqual(
            self.results(),
            [
                {
                    "date": "2026-03-12",
                    "reference": "2026-03-12",
                    "label": "jeudi 12 mars 2026",
                }
            ],
        )

    def test_plus_recentes_d_abord_filtrees_par_le_debut_de_la_date(self):
        for day in ("2026-03-12", "2026-04-01", "2025-03-30"):
            Note.objects.create(date=day, body="")

        self.assertEqual(
            [r["date"] for r in self.results()],
            ["2026-04-01", "2026-03-12", "2025-03-30"],
        )
        self.assertEqual([r["date"] for r in self.results(q="2026-03")], ["2026-03-12"])

    def test_lecture_seule(self):
        response = self.client.post(reverse("note_taking:note_suggestions"))

        self.assertEqual(response.status_code, 405)

    def test_adresse_sur_le_formulaire(self):
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assertIn(
            f'data-notes-url="{reverse("note_taking:note_suggestions")}"', html
        )
