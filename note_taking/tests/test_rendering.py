"""Tests du rendu HTML des notes : note parts et vue Markdown complète."""

import unittest

from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.icons import icon_svg
from core.models import Project
from images.models import Image
from note_taking.models import Note, NotePart
from note_taking.rendering import IMAGE_MISSING_PATH, render_markdown


class NotePartRenderingTests(TestCase):
    def render(self, content: str) -> str:
        return NotePart(project=Project(name="P"), content=content).rendered_content()

    def test_markdown_simple(self):
        self.assertHTMLEqual(
            self.render("Texte **gras**"), "<p>Texte <strong>gras</strong></p>"
        )

    def test_tableau(self):
        html = self.render("| a | b |\n|---|---|\n| 1 | 2 |")

        self.assertIn("<table>", html)
        self.assertIn("<td>1</td>", html)

    def test_bloc_de_code(self):
        html = self.render("```python\nx = 1\n```")

        self.assertIn('<code class="language-python">x = 1', html)

    def test_largeur_d_image_appliquee(self):
        html = self.render("![a](image:999){width=50%}")

        self.assertIn('style="width: 50%"', html)
        self.assertNotIn("{width", html)

    def test_identifiant_de_figure_applique(self):
        html = self.render("![a](image:999){#fig-banc}")

        self.assertIn('id="fig-banc"', html)
        self.assertNotIn("{#fig", html)


class LayoutRenderingTests(SimpleTestCase):
    """Blocs de mise en page Quarto : layout-ncol et columns (#101)."""

    FIGURE = (
        "::: {#fig-banc layout-ncol=2}\n\n"
        "![A](a.png)\n\n"
        "![B](b.png){#fig-banc-b}\n\n"
        "Légende du *banc*\n"
        ":::"
    )

    def test_figure_en_colonnes_avec_legende(self):
        html = render_markdown(self.FIGURE)

        self.assertHTMLEqual(
            html,
            '<figure class="my-2" id="fig-banc">'
            '<div class="grid grid-cols-2 gap-4 items-start">'
            '<div class="min-w-0"><p><img loading="lazy" decoding="async" alt="A" src="a.png"></p></div>'
            '<div class="min-w-0"><p><img loading="lazy" decoding="async" alt="B" id="fig-banc-b" src="b.png"></p></div>'
            "</div>"
            '<figcaption class="mt-2 text-sm text-center text-slate-600">'
            "<p>Légende du <em>banc</em></p>"
            "</figcaption>"
            "</figure>",
        )

    def test_colonnes_sans_identifiant_ni_legende(self):
        html = render_markdown("::: {layout-ncol=2}\n![A](a.png)\n\n![B](b.png)\n:::")

        self.assertIn('class="grid grid-cols-2 gap-4 items-start"', html)
        self.assertEqual(html.count('<div class="min-w-0">'), 2)
        self.assertNotIn("<figcaption", html)
        self.assertNotIn(":::", html)

    def test_nombre_de_colonnes(self):
        html = render_markdown("::: {layout-ncol=3}\n![A](a.png)\n:::")

        self.assertIn("grid-cols-3", html)

    def test_columns(self):
        html = render_markdown(
            "::: {.columns}\n"
            "::: {.column}\nGauche\n:::\n"
            '::: {.column width="40%"}\nDroite\n:::\n'
            ":::"
        )

        self.assertHTMLEqual(
            html,
            '<div class="flex gap-4 my-2">'
            '<div class="flex-1 min-w-0"><p>Gauche</p></div>'
            '<div class="min-w-0" style="flex: 0 1 40%"><p>Droite</p></div>'
            "</div>",
        )

    def test_bloc_imbrique_dans_un_callout(self):
        html = render_markdown(
            "::: {.callout-note}\n"
            "::: {layout-ncol=2}\n![A](a.png)\n:::\n"
            "Après la figure\n"
            ":::"
        )

        self.assertIn("grid-cols-2", html)
        self.assertNotIn(":::", html)
        self.assertRegex(
            html, r'(?s)class="callout-body">.*<p>Après la figure</p></div></div>$'
        )

    def test_bloc_dans_un_bloc_de_code_non_interprete(self):
        html = render_markdown("```\n::: {layout-ncol=2}\nx\n:::\n```")

        self.assertNotIn("grid", html)
        self.assertIn("::: {layout-ncol=2}", html)


class ImageMissingTests(SimpleTestCase):
    """L'image de remplacement d'une image supprimée existe dans les statiques (#55)."""

    def test_image_de_remplacement_presente(self):
        self.assertIsNotNone(finders.find(IMAGE_MISSING_PATH))


class SetextHeadingTests(SimpleTestCase):
    """Pas de titres « setext » : seuls les titres en # comptent (#124)."""

    def test_element_de_liste_vide_apres_un_element(self):
        html = render_markdown("- Deux exemples montrent la demande\n- ")

        self.assertHTMLEqual(
            html, "<ul><li>Deux exemples montrent la demande</li><li></li></ul>"
        )

    def test_texte_souligne_de_tirets_pas_un_titre(self):
        html = render_markdown("Texte\n---")

        self.assertNotIn("<h2>", html)

    def test_texte_souligne_de_egal_pas_un_titre(self):
        html = render_markdown("Titre\n=====")

        self.assertNotIn("<h1>", html)

    def test_trait_horizontal_isole_conserve(self):
        html = render_markdown("Texte\n\n---\n\nSuite")

        self.assertHTMLEqual(html, "<p>Texte</p><hr><p>Suite</p>")

    def test_titres_en_diese_conserves(self):
        self.assertHTMLEqual(render_markdown("## Titre"), "<h2>Titre</h2>")


class SubListRenderingTests(SimpleTestCase):
    """Sous-listes imbriquées comme dans Quarto (#229).

    Règle de Pandoc : un élément est imbriqué si son marqueur commence au moins
    à la colonne du texte de l'élément parent (2 après « - », 3 après « 1. »).
    Les résultats attendus sont ceux de Pandoc.
    """

    def test_puce_indentee_de_2_espaces(self):
        html = render_markdown("- a\n  - b\n- c")

        self.assertHTMLEqual(html, "<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>")

    def test_puce_indentee_de_3_espaces(self):
        html = render_markdown("- a\n   - b")

        self.assertHTMLEqual(html, "<ul><li>a<ul><li>b</li></ul></li></ul>")

    def test_puce_indentee_de_4_espaces(self):
        html = render_markdown("- a\n    - b")

        self.assertHTMLEqual(html, "<ul><li>a<ul><li>b</li></ul></li></ul>")

    def test_puce_indentee_de_1_espace_au_meme_niveau(self):
        html = render_markdown("- a\n - b")

        self.assertHTMLEqual(html, "<ul><li>a</li><li>b</li></ul>")

    def test_trois_niveaux_puis_retour(self):
        html = render_markdown("- a\n  - b\n    - c\n  - d")

        self.assertHTMLEqual(
            html,
            "<ul><li>a<ul><li>b<ul><li>c</li></ul></li><li>d</li></ul></li></ul>",
        )

    def test_retour_sous_la_colonne_de_la_sous_liste(self):
        # « c » est sous la colonne du texte de « b », mais pas sous celle de « a ».
        html = render_markdown("- a\n    - b\n  - c")

        self.assertHTMLEqual(html, "<ul><li>a<ul><li>b</li><li>c</li></ul></li></ul>")

    def test_puce_sous_un_numero_alignee_sur_le_texte(self):
        html = render_markdown("1. a\n   - b\n2. c")

        self.assertHTMLEqual(html, "<ol><li>a<ul><li>b</li></ul></li><li>c</li></ol>")

    def test_puce_sous_un_numero_avant_le_texte_hors_de_la_liste(self):
        html = render_markdown("1. a\n  - b\n2. c")

        self.assertHTMLEqual(
            html, '<ol><li>a</li></ol><ul><li>b</li></ul><ol start="2"><li>c</li></ol>'
        )

    def test_numero_sous_un_numero_avant_le_texte_au_meme_niveau(self):
        html = render_markdown("1. a\n  1. b\n2. c")

        self.assertHTMLEqual(html, "<ol><li>a</li><li>b</li><li>c</li></ol>")

    def test_marqueur_a_deux_chiffres(self):
        self.assertHTMLEqual(
            render_markdown("10. a\n    - b"),
            '<ol start="10"><li>a<ul><li>b</li></ul></li></ol>',
        )
        self.assertHTMLEqual(
            render_markdown("10. a\n   - b"),
            '<ol start="10"><li>a</li></ol><ul><li>b</li></ul>',
        )

    def test_liste_numerotee_sous_une_puce(self):
        html = render_markdown("- a\n  1. b\n  2. c")

        self.assertHTMLEqual(html, "<ul><li>a<ol><li>b</li><li>c</li></ol></li></ul>")

    def test_paragraphe_aligne_sur_le_texte_de_l_element(self):
        html = render_markdown("- a\n\n  suite\n- c")

        self.assertHTMLEqual(
            html, "<ul><li><p>a</p><p>suite</p></li><li><p>c</p></li></ul>"
        )

    def test_code_indente_dans_un_element(self):
        html = render_markdown("- a\n\n      code\n- c")

        self.assertHTMLEqual(
            html,
            "<ul><li><p>a</p><pre><code>code\n</code></pre></li><li><p>c</p></li></ul>",
        )

    def test_marqueur_sous_la_colonne_du_texte_et_a_4_espaces_reste_du_texte(self):
        # « 1. c » n'atteint pas le texte de « 2. b » (colonne 5) : à 4 espaces
        # du bord, il n'ouvre pas d'élément et s'ajoute au texte de « b ».
        html = render_markdown("1. a\n  2. b\n    1. c")

        self.assertHTMLEqual(html, "<ol><li>a</li><li>b\n1. c</li></ol>")

    def test_marqueur_a_4_espaces_au_dela_du_texte(self):
        self.assertHTMLEqual(
            render_markdown("- a\n      - b"), "<ul><li>a\n- b</li></ul>"
        )
        # Après une ligne vide, c'est du code dans l'élément.
        self.assertInHTML(
            "<pre><code>- b\n</code></pre>", render_markdown("- a\n\n      - b")
        )

    def test_sous_liste_dans_un_callout(self):
        html = render_markdown("::: {.callout-note}\n- a\n  - b\n:::")

        self.assertInHTML("<ul><li>a<ul><li>b</li></ul></li></ul>", html)

    def test_liste_collee_a_un_paragraphe_reste_du_texte(self):
        html = render_markdown("Texte\n- a\n  - b")

        self.assertNotIn("<li>", html)

    def test_bloc_de_code_delimite_inchange(self):
        html = render_markdown("```\n- a\n  - b\n```")

        self.assertIn("<code>- a\n  - b\n</code>", html)


class TaskListRenderingTests(SimpleTestCase):
    """Cases à cocher « - [ ] » et « - [x] » comme dans Quarto (#231).

    Les résultats attendus sont ceux de Pandoc, avec des cases désactivées : la
    page affiche la note, elle ne la modifie pas.
    """

    def test_cases_cochee_et_non_cochee(self):
        html = render_markdown("- [ ] a\n- [x] b\n- [X] c")

        self.assertHTMLEqual(
            html,
            '<ul class="task-list">'
            '<li><label><input type="checkbox" disabled>a</label></li>'
            '<li><label><input type="checkbox" checked disabled>b</label></li>'
            '<li><label><input type="checkbox" checked disabled>c</label></li>'
            "</ul>",
        )

    def test_liste_mixte_sans_classe(self):
        html = render_markdown("- [ ] a\n- b")

        self.assertHTMLEqual(
            html,
            '<ul><li><label><input type="checkbox" disabled>a</label></li>'
            "<li>b</li></ul>",
        )

    def test_liste_numerotee(self):
        html = render_markdown("1. [ ] a\n2. [x] b")

        self.assertHTMLEqual(
            html,
            '<ol><li><label><input type="checkbox" disabled>a</label></li>'
            '<li><label><input type="checkbox" checked disabled>b</label></li></ol>',
        )

    def test_mise_en_forme_dans_le_libelle(self):
        html = render_markdown("- [ ] **gras** et `code`")

        self.assertInHTML(
            '<label><input type="checkbox" disabled><strong>gras</strong> et '
            "<code>code</code></label>",
            html,
        )

    def test_libelle_arrete_avant_la_sous_liste(self):
        html = render_markdown("- [ ] a\n  - b\n  - [x] c")

        self.assertHTMLEqual(
            html,
            '<ul class="task-list"><li><label><input type="checkbox" disabled>a'
            "</label><ul><li>b</li>"
            '<li><label><input type="checkbox" checked disabled>c</label></li>'
            "</ul></li></ul>",
        )

    def test_sous_liste_de_cases(self):
        html = render_markdown("- a\n  - [ ] b")

        self.assertHTMLEqual(
            html,
            '<ul><li>a<ul class="task-list">'
            '<li><label><input type="checkbox" disabled>b</label></li>'
            "</ul></li></ul>",
        )

    def test_liste_lache(self):
        html = render_markdown("- [ ] a\n\n  suite")

        self.assertHTMLEqual(
            html,
            '<ul class="task-list"><li><p><label><input type="checkbox" disabled>a'
            "</label></p><p>suite</p></li></ul>",
        )

    def test_blancs_apres_la_case_retires(self):
        for text in ("- [x]  a", "- [x]\ta", "- \[x] a", "- [x] a\r\n"):
            with self.subTest(text=text):
                self.assertHTMLEqual(
                    render_markdown(text),
                    '<ul class="task-list"><li><label>'
                    '<input type="checkbox" checked disabled>a</label></li></ul>',
                )

    def test_crochets_sans_case(self):
        for text, expected in (
            ("- [ ]a", "<ul><li>[ ]a</li></ul>"),
            ("- [ ]", "<ul><li>[ ]</li></ul>"),
            ("- [] a", "<ul><li>[] a</li></ul>"),
            ("- a [ ] b", "<ul><li>a [ ] b</li></ul>"),
            ("[ ] a", "<p>[ ] a</p>"),
        ):
            with self.subTest(text=text):
                self.assertHTMLEqual(render_markdown(text), expected)

    def test_bloc_de_code_inchange(self):
        html = render_markdown("```\n- [ ] a\n```")

        self.assertIn("<code>- [ ] a\n</code>", html)

    def test_dans_un_callout(self):
        html = render_markdown("::: {.callout-note}\n- [x] a\n:::")

        self.assertInHTML(
            '<label><input type="checkbox" checked disabled>a</label>', html
        )


TABLE = "| a |\n|---|\n| 1 |"
TABLE_BODY = "<thead><tr><th>a</th></tr></thead><tbody><tr><td>1</td></tr></tbody>"


class TableCaptionRenderingTests(SimpleTestCase):
    """Légendes de tableau « : Légende » comme dans Quarto (#230).

    Les résultats attendus sont ceux de Pandoc : un paragraphe qui commence par
    « : » ou « Table: », juste avant ou juste après un tableau, en est la légende.
    """

    def assertCaption(self, text: str, caption: str, attrs: str = ""):
        self.assertHTMLEqual(
            render_markdown(text),
            f"<table{attrs}><caption>{caption}</caption>{TABLE_BODY}</table>",
        )

    @unittest.expectedFailure
    def test_legende_apres_le_tableau(self):
        self.assertCaption(
            f"{TABLE}\n\n: Rétreint **thermique**",
            "Rétreint <strong>thermique</strong>",
        )

    @unittest.expectedFailure
    def test_legende_avant_le_tableau(self):
        self.assertCaption(f": Avant\n\n{TABLE}", "Avant")

    @unittest.expectedFailure
    def test_legende_collee_au_tableau(self):
        self.assertCaption(f"{TABLE}\n: Après", "Après")
        self.assertCaption(f": Avant\n{TABLE}", "Avant")

    @unittest.expectedFailure
    def test_formes_de_la_legende(self):
        for text in (": L", ":L", "Table: L", "table: L", "\n: L"):
            with self.subTest(text=text):
                self.assertCaption(f"{TABLE}\n\n{text}", "L")

    @unittest.expectedFailure
    def test_legende_sur_plusieurs_lignes(self):
        self.assertCaption(f"{TABLE}\n\n: deux\nlignes", "deux\nlignes")

    @unittest.expectedFailure
    def test_attributs_reportes_sur_le_tableau(self):
        self.assertCaption(
            f"{TABLE}\n\n: L {{#tbl-x .large}}", "L", ' id="tbl-x" class="large"'
        )

    @unittest.expectedFailure
    def test_legende_d_avant_prioritaire(self):
        html = render_markdown(f": avant\n\n{TABLE}\n\n: après")

        self.assertHTMLEqual(
            html,
            f"<table><caption>avant</caption>{TABLE_BODY}</table><p>: après</p>",
        )

    @unittest.expectedFailure
    def test_legende_entre_deux_tableaux_au_premier(self):
        html = render_markdown(f"{TABLE}\n\n: L\n\n{TABLE}")

        self.assertHTMLEqual(
            html,
            f"<table><caption>L</caption>{TABLE_BODY}</table>"
            f"<table>{TABLE_BODY}</table>",
        )

    @unittest.expectedFailure
    def test_legende_dans_un_callout(self):
        html = render_markdown(f"::: {{.callout-note}}\n{TABLE}\n\n: L\n:::")

        self.assertInHTML(f"<table><caption>L</caption>{TABLE_BODY}</table>", html)

    def test_paragraphe_sans_tableau_voisin(self):
        for text in ("Texte\n\n: pas de tableau", f"{TABLE}\n\nTexte\n\n: loin"):
            with self.subTest(text=text):
                html = render_markdown(text)

                self.assertNotIn("<caption>", html)
                self.assertIn("<p>: ", html)

    def test_bloc_de_code_inchange(self):
        html = render_markdown(f"```\n{TABLE}\n: L\n```")

        self.assertIn(f"<code>{TABLE}\n: L\n</code>", html)


class CalloutRenderingTests(SimpleTestCase):
    def test_titre_en_attribut(self):
        html = render_markdown(
            '::: {.callout-warning title="Attention !"}\nTexte **gras**\n:::'
        )

        self.assertHTMLEqual(
            html,
            '<div class="callout callout-warning">'
            '<div class="callout-header">'
            f"{icon_svg('warning', 'callout-icon')}"
            '<span class="callout-title">Attention !</span>'
            "</div>"
            '<div class="callout-body"><p>Texte <strong>gras</strong></p></div>'
            "</div>",
        )

    def test_titre_depuis_le_premier_titre_markdown(self):
        html = render_markdown("::: {.callout-tip}\n\n## Mon titre\nTexte\n:::")

        self.assertInHTML('<span class="callout-title">Mon titre</span>', html)
        self.assertNotIn("<h2>", html)

    def test_titre_par_defaut_du_type(self):
        for callout_type, title in (
            ("note", "Note"),
            ("tip", "Astuce"),
            ("warning", "Avertissement"),
            ("caution", "Attention"),
            ("important", "Important"),
        ):
            with self.subTest(callout_type=callout_type):
                html = render_markdown(f"::: {{.callout-{callout_type}}}\nx\n:::")

                self.assertInHTML(f'<span class="callout-title">{title}</span>', html)

    def test_texte_autour_du_callout(self):
        html = render_markdown("Avant\n\n::: {.callout-note}\nDedans\n:::\n\nAprès")

        self.assertHTMLEqual(
            html,
            "<p>Avant</p>"
            '<div class="callout callout-note">'
            '<div class="callout-header">'
            f"{icon_svg('info', 'callout-icon')}"
            '<span class="callout-title">Note</span>'
            "</div>"
            '<div class="callout-body"><p>Dedans</p></div>'
            "</div>"
            "<p>Après</p>",
        )

    def test_icone_par_type(self):
        for callout_type, icon in (
            ("note", "info"),
            ("tip", "lightbulb"),
            ("warning", "warning"),
            ("caution", "report"),
            ("important", "error"),
        ):
            with self.subTest(callout_type=callout_type):
                html = render_markdown(f"::: {{.callout-{callout_type}}}\nx\n:::")

                self.assertInHTML(icon_svg(icon, "callout-icon"), html)

    def test_sans_icone_avec_icon_false(self):
        html = render_markdown("::: {.callout-note icon=false}\nx\n:::")

        self.assertNotIn("callout-icon", html)

    def test_sans_icone_pour_un_type_inconnu(self):
        html = render_markdown("::: {.callout-autre}\nx\n:::")

        self.assertIn('class="callout callout-autre"', html)
        self.assertNotIn("callout-icon", html)

    def test_titre_echappe(self):
        html = render_markdown('::: {.callout-note title="<b>x</b>"}\ny\n:::')

        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)

    def test_callout_dans_un_bloc_de_code_non_interprete(self):
        html = render_markdown("```\n::: {.callout-note}\nx\n:::\n```")

        self.assertNotIn('class="callout', html)
        self.assertIn("::: {.callout-note}", html)

    def test_callout_non_ferme_laisse_tel_quel(self):
        html = render_markdown("::: {.callout-note}\nx")

        self.assertNotIn('class="callout', html)

    def test_rendu_d_une_note_part(self):
        part = NotePart(
            project=Project(name="P"),
            content='::: {.callout-note title="Remarque"}\nContenu\n:::',
        )

        self.assertInHTML(
            '<span class="callout-title">Remarque</span>', part.rendered_content()
        )


class NoteMarkdownViewTests(TestCase):
    def test_rendu_du_contenu_complet(self):
        note = Note.objects.create(date="2025-11-24", body="# P\n\n| a |\n|---|\n| 1 |")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "<h2>P</h2>", html=True)
        self.assertContains(response, "<td>1</td>", html=True)
        self.assertEqual(str(response.context["date"]), "2025-11-24")

    def get(self, body: str):
        note = Note.objects.create(date="2025-11-24", body=body)
        return self.client.get(reverse("note_taking:note_md", args=[note.pk]))

    def test_image_resolue_par_nom_de_fichier(self):
        image = Image.objects.create(name="banc.png", file="note_images/banc.png")

        response = self.get("![Banc](images/banc.png){width=80%}")

        self.assertContains(
            response,
            f'<img loading="lazy" decoding="async" alt="Banc" src="{image.file.url}" style="width: 80%">',
            html=True,
        )

    def test_image_inconnue_remplacee(self):
        response = self.get("![Banc](images/inconnue.png)")

        self.assertContains(
            response,
            f'<img loading="lazy" decoding="async" alt="Banc" src="{static(IMAGE_MISSING_PATH)}">',
            html=True,
        )

    def test_bloc_metadata_retire(self):
        response = self.get("Avant\n\n::: {.metadata}\ntags: a\n:::\n\nAprès")

        self.assertContains(response, "<p>Avant</p>", html=True)
        self.assertContains(response, "<p>Après</p>", html=True)
        self.assertNotContains(response, "metadata")
        self.assertNotContains(response, "tags: a")

    def test_bloc_metadata_conserve_dans_un_bloc_de_code(self):
        response = self.get("```\n::: {.metadata}\ntags: a\n:::\n```")

        self.assertContains(response, "tags: a")

    def test_note_sans_contenu(self):
        note = Note.objects.create(date="2025-11-24", body="")

        response = self.client.get(reverse("note_taking:note_md", args=[note.pk]))

        self.assertContains(response, "Aucun contenu disponible.")

    def test_note_inexistante(self):
        response = self.client.get(reverse("note_taking:note_md", args=[999]))

        self.assertEqual(response.status_code, 404)
