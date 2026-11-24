"""Capture rapide (#386) : une ligne ajoutée à la note du jour, à sa place, depuis
n'importe quelle page."""

import re
from unittest import expectedFailure

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project, Section
from note_taking.models import Note
from note_taking.services import process_passages
from todolist.models import Task


def key_of(body: str, title: str, occurrence: int = 0) -> str:
    """La clé, dans le plan, du titre `title` de ce texte."""
    from note_taking.quick_capture import targets

    found = [target.key for target in targets(body) if target.title == title]
    return found[occurrence]


def add(body: str, text: str, target: str = "", **options) -> str:
    """Le texte de la note après la capture de `text` sous le titre `target`."""
    from note_taking.quick_capture import add_to_body

    key = key_of(body, target, options.pop("occurrence", 0)) if target else ""
    return add_to_body(body, text, key=key, **options)


class PlanTests(SimpleTestCase):
    @expectedFailure
    def test_titres_de_la_note_avec_leur_profondeur(self):
        from note_taking.quick_capture import targets

        body = "x\n# P {#p}\n## A\n```\n# non\n```\n# Q"

        self.assertEqual(
            [(t.title, t.depth, t.project, t.path) for t in targets(body)],
            [("P", 0, "P", ()), ("A", 1, "P", ("A",)), ("Q", 0, "Q", ())],
        )

    @expectedFailure
    def test_titres_repetes_distingues(self):
        body = "# P\n## A\nx\n## A\ny"

        self.assertNotEqual(key_of(body, "A"), key_of(body, "A", 1))

    @expectedFailure
    def test_cle_stable_quand_la_note_change_ailleurs(self):
        self.assertEqual(key_of("# P\n## A\nx", "A"), key_of("y\n# P\nz\n## A\nx", "A"))


class PlaceTests(SimpleTestCase):
    @expectedFailure
    def test_en_tete_sans_projet(self):
        self.assertEqual(add("", "Idée"), "Idée\n")
        self.assertEqual(add("# P\nx", "Idée"), "Idée\n\n# P\nx")
        self.assertEqual(add("a\n\n# P\nx", "Idée"), "a\n\nIdée\n\n# P\nx")

    @expectedFailure
    def test_en_fin_de_section_avant_les_sous_titres(self):
        self.assertEqual(
            add("# P\na\n\n## A\nb\n# Q", "Idée", "P"),
            "# P\na\n\nIdée\n\n## A\nb\n# Q",
        )
        self.assertEqual(
            add("# P\na\n## A\nb\n# Q", "Idée", "A"),
            "# P\na\n## A\nb\n\nIdée\n\n# Q",
        )

    @expectedFailure
    def test_en_fin_de_note(self):
        self.assertEqual(add("# P\na", "Idée", "P"), "# P\na\n\nIdée")
        self.assertEqual(add("# P\na\n", "Idée", "P"), "# P\na\n\nIdée\n")

    @expectedFailure
    def test_jamais_colle_a_un_titre(self):
        self.assertEqual(
            add("# P\n## A\n## B", "Idée", "A"), "# P\n## A\n\nIdée\n\n## B"
        )

    @expectedFailure
    def test_titre_repete(self):
        self.assertEqual(
            add("# P\n## A\nx\n## A\ny", "Idée", "A", occurrence=1),
            "# P\n## A\nx\n## A\ny\n\nIdée",
        )

    @expectedFailure
    def test_apres_un_bloc_et_pas_dedans(self):
        blocks = (
            "```python\n# x\n```",
            "~~~\nx\n~~~",
            "::: {.callout-note}\n## Titre\ntexte\n:::",
            "::: {.metadata}\ntags: [a]\n:::",
            ":::: {.columns}\n::: {.column}\na\n:::\n::::",
        )
        for block in blocks:
            with self.subTest(block=block):
                self.assertEqual(
                    add(f"# P\n{block}\n# Q", "Idée", "P"),
                    f"# P\n{block}\n\nIdée\n\n# Q",
                )

    @expectedFailure
    def test_bloc_jamais_ferme_la_ligne_est_avant(self):
        self.assertEqual(
            add("# P\na\n::: {.callout-note}\nb", "Idée", "P"),
            "# P\na\n\nIdée\n\n::: {.callout-note}\nb",
        )

    @expectedFailure
    def test_titre_dans_une_colonne(self):
        """La section s'arrête à la fin de la colonne qui contient le titre."""
        self.assertEqual(
            add("# P\n::: {.column}\n## A\na\n:::\nz", "Idée", "A"),
            "# P\n::: {.column}\n## A\na\n\nIdée\n:::\nz",
        )

    @expectedFailure
    def test_fins_de_ligne_gardees(self):
        self.assertEqual(
            add("# P\r\na\r\n# Q\r\nb", "Un\nDeux", "P"),
            "# P\r\na\r\n\r\nUn\r\nDeux\r\n\r\n# Q\r\nb",
        )
        self.assertEqual(add("# P\r\na", "Un", "P"), "# P\r\na\r\n\r\nUn")


class TextTests(SimpleTestCase):
    @expectedFailure
    def test_tache(self):
        self.assertEqual(
            add("# P", "Relancer", "P", is_task=True), "# P\n\n- [ ] Relancer"
        )

    @expectedFailure
    def test_tache_deja_ecrite_comme_telle(self):
        for text in ("- Relancer", "- [ ] Relancer", "* [x] Relancer"):
            with self.subTest(text=text):
                self.assertEqual(add("", text, is_task=True), "- [ ] Relancer\n")

    @expectedFailure
    def test_suite_d_une_tache_dans_son_element(self):
        self.assertEqual(add("", "Un\r\nDeux", is_task=True), "- [ ] Un\n  Deux\n")

    @expectedFailure
    def test_tache_a_la_suite_d_une_liste(self):
        self.assertEqual(
            add("# P\n- [ ] a\n    - b\n# Q", "c", "P", is_task=True),
            "# P\n- [ ] a\n    - b\n- [ ] c\n\n# Q",
        )

    @expectedFailure
    def test_texte_apres_une_liste_et_tache_apres_un_texte(self):
        self.assertEqual(add("# P\n- a", "b", "P"), "# P\n- a\n\nb")
        self.assertEqual(add("# P\na", "b", "P", is_task=True), "# P\na\n\n- [ ] b")
        self.assertEqual(
            add("# P\n1. a", "b", "P", is_task=True), "# P\n1. a\n\n- [ ] b"
        )

    @expectedFailure
    def test_texte_vide_refuse(self):
        from note_taking.exceptions import QuickCaptureError

        for text in ("", "  \n "):
            with self.assertRaises(QuickCaptureError):
                add("# P", text)

    @expectedFailure
    def test_texte_qui_changerait_la_structure_refuse(self):
        from note_taking.exceptions import QuickCaptureError

        for text in (
            "# Titre",
            "x\n  ## Titre",
            "```\nx",
            "~~~",
            "::: {.callout-note}",
            "x\n:::",
            "---",
            "x\n===",
        ):
            with self.subTest(text=text), self.assertRaises(QuickCaptureError):
                add("# P", text, "P")

    @expectedFailure
    def test_diese_dans_le_texte_permis(self):
        self.assertEqual(add("", "Voir #386 et C# 14"), "Voir #386 et C# 14\n")


class NewTitleTests(SimpleTestCase):
    @expectedFailure
    def test_nouveau_projet_en_fin_de_note(self):
        self.assertEqual(add("", "x", new_title="P"), "# P\n\nx\n")
        self.assertEqual(
            add("a\n# P\nb", "x", new_title=" Nouveau  projet "),
            "a\n# P\nb\n\n# Nouveau projet\n\nx",
        )

    @expectedFailure
    def test_nouveau_niveau_apres_les_sous_titres(self):
        self.assertEqual(
            add("# P\na\n## A\nb\n# Q", "x", "P", new_title="B"),
            "# P\na\n## A\nb\n\n## B\n\nx\n\n# Q",
        )

    @expectedFailure
    def test_titre_deja_ecrit_repris_casse_ignoree(self):
        body = "# P\n## Réunion\na\n# Q"

        self.assertEqual(
            add(body, "x", "P", new_title="réunion"),
            "# P\n## Réunion\na\n\nx\n\n# Q",
        )
        self.assertEqual(add(body, "x", new_title="q"), body + "\n\nx")

    @expectedFailure
    def test_sous_un_dernier_niveau_refuse(self):
        from note_taking.exceptions import QuickCaptureError

        with self.assertRaises(QuickCaptureError):
            add("# P\n###### F", "x", "F", new_title="G")

    @expectedFailure
    def test_bloc_jamais_ferme_refuse(self):
        """Le titre y serait perdu, ou prendrait la suite de la note."""
        from note_taking.exceptions import QuickCaptureError

        for body in ("# P\n```\na", "# P\n::: {.callout-note}\na"):
            with self.subTest(body=body), self.assertRaises(QuickCaptureError):
                add(body, "x", new_title="Q")

    @expectedFailure
    def test_titre_trop_long_refuse(self):
        from note_taking.exceptions import QuickCaptureError

        with self.assertRaises(QuickCaptureError):
            add("", "x", new_title="A" * 201)


class CaptureTestCase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

    @property
    def url(self) -> str:
        return reverse("note_taking:quick_capture")

    def note(self, body: str) -> Note:
        note = Note.objects.create(date=self.today, body=body)
        process_passages(note)
        return note

    def post(self, text: str, **fields):
        return self.client.post(
            self.url, {"text": text, **fields}, headers={"HX-Request": "true"}
        )


class CaptureViewTests(CaptureTestCase):
    @expectedFailure
    def test_note_absente_creee_avec_la_ligne(self):
        response = self.post("Idée")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Note.objects.get(date=self.today).body, "Idée\n")

    @expectedFailure
    def test_ajout_a_la_note_du_jour(self):
        note = self.note("# P\na")

        self.post("Idée", target=key_of(note.body, "P"))

        note.refresh_from_db()
        self.assertEqual(note.body, "# P\na\n\nIdée")
        self.assertIn("Idée", note.passages.get().content)

    @expectedFailure
    def test_toast_avec_un_lien_vers_la_note(self):
        html = self.post("Idée").content.decode()

        self.assertIn("data-toast", html)
        url = reverse("note_taking:note_detail", args=[self.today])
        self.assertIn(f'<a href="{url}">note du jour</a>', html)

    @expectedFailure
    def test_tache_a_revoir_avec_un_lien_vers_le_bilan(self):
        html = self.post("Relancer", is_task="on").content.decode()

        task = Task.objects.get()
        self.assertEqual(
            (task.title, task.note_state), ("Relancer", Task.NoteState.TO_REVIEW)
        )
        url = reverse("todolist:note_review", args=[self.today])
        self.assertIn(f'<a href="{url}">1 tâche à revoir</a>', html)

    @expectedFailure
    def test_nouveau_titre_projet_et_niveau_crees(self):
        note = self.note("# P\na")

        self.post("x", target=key_of(note.body, "P"), new_title="A")
        self.post("y", new_title="Q")

        self.assertEqual(Section.objects.get().name, "A")
        self.assertEqual(
            sorted(Project.objects.values_list("name", flat=True)), ["P", "Q"]
        )

    @expectedFailure
    def test_titre_disparu_rien_n_est_ecrit(self):
        note = self.note("# P\n## A\na")
        key = key_of(note.body, "A")
        Note.objects.update(body="# P\na")

        response = self.post("Idée", target=key)

        self.assertEqual(response.status_code, 422)
        self.assertIn("a changé", response.content.decode())
        self.assertEqual(Note.objects.get().body, "# P\na")

    @expectedFailure
    def test_texte_refuse(self):
        response = self.post("# Titre")

        self.assertEqual(response.status_code, 422)
        self.assertIn("data-toast", response.content.decode())
        self.assertFalse(Note.objects.exists())

    @expectedFailure
    def test_erreur_d_analyse_rien_n_est_ecrit(self):
        note = self.note("# P\na")

        response = self.post("![](images/absente.png)")

        self.assertEqual(response.status_code, 422)
        note.refresh_from_db()
        self.assertEqual(note.body, "# P\na")
        self.assertEqual(note.passages.count(), 1)

    @expectedFailure
    def test_titre_echappe_dans_le_plan(self):
        self.note("# <b>P</b>\na")

        html = self.client.get(
            self.url, headers={"HX-Request": "true"}
        ).content.decode()

        self.assertIn("&lt;b&gt;P&lt;/b&gt;", html)
        self.assertNotIn("<b>P</b>", html)

    @expectedFailure
    def test_plan_de_la_note_du_jour(self):
        note = self.note("# P\n## A\na")

        response = self.client.get(self.url, headers={"HX-Request": "true"})

        html = response.content.decode()
        self.assertNotIn("<html", html)
        for title in ("P", "A"):
            self.assertIn(f'value="{key_of(note.body, title)}"', html)
        self.assertRegex(html, r'data-project="P"[^>]*data-path="A"')

    @expectedFailure
    def test_plan_sans_note_du_jour(self):
        response = self.client.get(self.url, headers={"HX-Request": "true"})

        self.assertContains(response, "sera créée")

    @expectedFailure
    def test_sans_javascript_le_formulaire_de_la_note_du_jour(self):
        self.assertRedirects(
            self.client.get(self.url),
            reverse("note_taking:new_note") + f"?date={self.today}",
        )
        self.note("x")
        self.assertRedirects(
            self.client.get(self.url),
            reverse("note_taking:edit_note", args=[self.today]),
        )


class HeaderTests(CaptureTestCase):
    PAGES = ("core:index", "core:projects", "note_taking:index", "todolist:task_list")

    @expectedFailure
    def test_bouton_et_dialogue_sur_toutes_les_pages(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                end = html[html.index('id="header-end"') :].split("</header>")[0]
                link = re.search(r"<a [^>]*data-quick-capture[^>]*>", end)
                assert link is not None
                self.assertIn(f'href="{self.url}"', link[0])
                self.assertIn(
                    'aria-keyshortcuts="Control+Shift+K Meta+Shift+K"', link[0]
                )
                self.assertIn("<dialog", end)
                self.assertIn("quick_capture.js", html)

    @expectedFailure
    def test_choix_par_defaut_en_tete_sans_projet(self):
        html = self.client.get(reverse("core:index")).content.decode()

        self.assertRegex(
            html, r'<input type="radio" name="target" value=""[^>]*checked'
        )

    @expectedFailure
    def test_le_plan_n_est_pas_lu_a_chaque_page(self):
        """Une page quelconque ne lit pas la note du jour pour le dialogue."""
        self.note("# PlanDuJour\na")

        html = self.client.get(reverse("note_taking:images_list")).content.decode()

        self.assertIn("<dialog", html)
        self.assertNotIn("PlanDuJour", html)
