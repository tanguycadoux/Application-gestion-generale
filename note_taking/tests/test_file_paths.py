"""Lien vers un fichier local ou réseau (#496) : le texte du lien et un bouton « Copier le
chemin », écart voulu à Pandoc (un navigateur n'ouvre pas un fichier depuis une page)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.models import Note
from note_taking.rendering import render_note_body, render_passage
from note_taking.rendering.headings import heading_texts
from note_taking.tests.links import new_tab_link

BUTTON_REGEX = re.compile(
    r'<button type="button" class="file-path-copy[^"]*" data-copy-path="(?P<path>[^"]*)"'
    r' title="(?P<title>[^"]*)" aria-label="(?P<label>[^"]*)">.*?</button>',
    re.DOTALL,
)


def copied_path(html: str) -> str:
    """Le chemin que copie le seul bouton de ce HTML, échappé comme dans la page."""
    buttons = BUTTON_REGEX.findall(html)
    assert len(buttons) == 1, html
    path, title, _ = buttons[0]
    assert path == title, html
    return path


class FilePathFormsTests(SimpleTestCase):
    def test_chaque_forme_de_chemin_copiee_en_chemin_windows(self):
        for target, path in (
            ("C:\\Docs\\plan.pdf", "C:\\Docs\\plan.pdf"),
            ("C:/Docs/plan.pdf", "C:\\Docs\\plan.pdf"),
            ("c:\\docs\\plan.pdf", "c:\\docs\\plan.pdf"),
            ("file:///C:/Docs/plan.pdf", "C:\\Docs\\plan.pdf"),
            ("\\\\serveur\\partage\\plan.pdf", "\\\\serveur\\partage\\plan.pdf"),
            ("//serveur/partage/plan.pdf", "\\\\serveur\\partage\\plan.pdf"),
            ("file://serveur/partage/plan.pdf", "\\\\serveur\\partage\\plan.pdf"),
            ("file:////serveur/partage/plan.pdf", "\\\\serveur\\partage\\plan.pdf"),
            ("FILE:///C:/Docs/plan.pdf", "C:\\Docs\\plan.pdf"),
        ):
            with self.subTest(target=target):
                html = render_passage(f"Voir [le plan]({target}).")

                self.assertNotIn("<a", html)
                self.assertIn('<span class="file-path">le plan<button', html)
                self.assertEqual(copied_path(html), path)
                self.assertTrue(html.endswith("</span>.</p>"), html)

    def test_adresse_file_decodee(self):
        html = render_passage("[plan](file:///C:/Mes%20documents/plan%C3%A9.pdf)")

        self.assertEqual(copied_path(html), "C:\\Mes documents\\plané.pdf")

    def test_chemin_linux_d_une_adresse_file(self):
        html = render_passage("[plan](file:///home/moi/plan.pdf)")

        self.assertEqual(copied_path(html), "/home/moi/plan.pdf")

    def test_chemin_avec_espaces_entre_chevrons(self):
        for text in (
            "[plan](<C:\\Mes documents\\plan.pdf>)",
            "[plan](C:\\Mes documents\\plan.pdf)",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    copied_path(render_passage(text)), "C:\\Mes documents\\plan.pdf"
                )

    def test_barres_obliques_inversees_gardees(self):
        """Le Markdown lirait `\\\\` comme une barre échappée : le chemin est lu avant."""
        html = render_passage("[plan](\\\\serveur\\partage\\_a_\\*b*\\plan.pdf)")

        self.assertEqual(copied_path(html), "\\\\serveur\\partage\\_a_\\*b*\\plan.pdf")

    def test_libelle_et_info_bulle(self):
        html = render_passage("[le plan](C:\\Docs\\plan.pdf)")
        _, title, label = BUTTON_REGEX.findall(html)[0]

        self.assertEqual(title, "C:\\Docs\\plan.pdf")
        self.assertEqual(label, "Copier le chemin de plan.pdf")
        self.assertIn('aria-hidden="true"', html)

    def test_sans_texte_le_nom_du_fichier(self):
        for text, name in (
            ("[](C:\\Docs\\plan_v2_final.pdf)", "plan_v2_final.pdf"),
            ("[ ](file:///C:/Docs/plan%20a.pdf)", "plan a.pdf"),
            ("[](\\\\serveur\\partage\\dossier\\)", "dossier"),
            ("[](C:\\)", "C:\\"),
        ):
            with self.subTest(text=text):
                self.assertIn(
                    f'<span class="file-path">{name}<button', render_passage(text)
                )

    def test_texte_du_lien_mis_en_forme(self):
        html = render_passage("[le *plan* `v2`](C:\\Docs\\plan.pdf)")

        self.assertIn(
            '<span class="file-path">le <em>plan</em> <code>v2</code><button', html
        )

    def test_chemin_echappe(self):
        html = render_passage("[plan](<C:\\R&D\\<b>.pdf>)")

        self.assertNotIn("<b>", html)
        self.assertEqual(
            copied_path(render_passage("[p](C:\\R&D\\a.pdf)")), "C:\\R&amp;D\\a.pdf"
        )

    def test_autres_liens_inchanges(self):
        for target in (
            "https://exemple.org/a",
            "/home/moi/plan.pdf",
            "~/plan.pdf",
            "plan.pdf",
            "#ancre",
        ):
            with self.subTest(target=target):
                html = render_passage(f"[plan]({target})")

                self.assertNotIn("file-path", html)
                self.assertIn(f'href="{target}"', html)
        self.assertIn(
            new_tab_link("https://exemple.org/a", "plan"),
            render_passage("[plan](https://exemple.org/a)"),
        )

    def test_code_image_et_crochet_echappe_inchanges(self):
        for text in (
            "`[plan](C:\\Docs\\plan.pdf)`",
            "```\n[plan](C:\\Docs\\plan.pdf)\n```",
            "    [plan](C:\\Docs\\plan.pdf)",
            "\\[plan](C:\\Docs\\plan.pdf)",
            "![plan](C:\\Docs\\plan.png)",
        ):
            with self.subTest(text=text):
                self.assertNotIn("file-path", render_passage(text))

    def test_titre_sans_le_bouton(self):
        """Ni l'identifiant ni le plan d'un titre ne contiennent le bouton."""
        html = render_note_body("# Voir [plan](C:\\Docs\\plan.pdf)", heading_ids=True)

        self.assertEqual(heading_texts(html), [("Voir plan", "voir-plan")])
        self.assertIn("data-copy-path", html)


class FilePathPagesTests(TestCase):
    def test_page_d_une_note(self):
        Note.objects.create(date="2026-03-12", body="[plan](C:\\Docs\\plan.pdf)")

        html = self.client.get(
            reverse("note_taking:note_detail", args=["2026-03-12"])
        ).content.decode()

        self.assertEqual(
            copied_path(html.split("rendered-content", 1)[1]), "C:\\Docs\\plan.pdf"
        )
        self.assertIn("note_taking/file_paths.js", html)

    def test_script_charge_dans_la_recherche(self):
        html = self.client.get(reverse("note_taking:notes_search")).content.decode()

        self.assertIn("note_taking/file_paths.js", html)


class FilePathScriptTests(SimpleTestCase):
    """Ce que le script promet (il n'est pas exécuté par les tests)."""

    def read(self) -> str:
        path = Path(settings.BASE_DIR, "note_taking", "static", "note_taking")
        return (path / "file_paths.js").read_text(encoding="utf-8")

    def test_copie_avec_repli_hors_contexte_securise(self):
        script = self.read()

        self.assertIn("[data-copy-path]", script)
        self.assertIn("navigator.clipboard.writeText", script)
        self.assertIn("isSecureContext", script)
        self.assertIn('document.execCommand("copy")', script)
        self.assertIn('Toast.show("Chemin copié.", "success")', script)

    def test_chemin_imprime_a_la_place_du_bouton(self):
        css = Path(
            settings.BASE_DIR, "note_taking", "static", "note_taking", "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn('content: " (" attr(data-copy-path) ")"', css)
