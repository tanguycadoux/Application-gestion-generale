"""Résultats de recherche groupés par note, avec extraits surlignés (#201)."""

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from note_taking.models import Note, NotePart
from note_taking.search import group_by_note, search_note_parts
from note_taking.search_index import snippets
from note_taking.search_query import parse_query


class SnippetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.note = Note.objects.create(date="2026-10-15")

    def part(self, content, heading_path=""):
        return NotePart.objects.create(
            note=self.note,
            project=self.project,
            content=content,
            heading_path=heading_path,
        )

    def test_terme_surligne(self):
        part = self.part("Le banc thermique est prêt")

        result = snippets('"thermique"', [part.pk])

        self.assertEqual(set(result), {part.pk})
        self.assertIn("<mark>thermique</mark>", result[part.pk])

    def test_html_du_texte_echappe(self):
        part = self.part("<script>alert(1)</script> banc & co")

        html = snippets('"banc"', [part.pk])[part.pk]

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("<mark>banc</mark>", html)
        self.assertIn("&amp;", html)

    def test_extrait_court_sur_un_long_texte(self):
        part = self.part("début " * 200 + "aiguille " + "fin " * 200)

        html = snippets('"aiguille"', [part.pk])[part.pk]

        self.assertIn("<mark>aiguille</mark>", html)
        self.assertLess(len(html), 400)
        self.assertIn("…", html)

    def test_prefixe_et_phrase(self):
        part = self.part("la résistance thermique mesurée")

        self.assertIn(
            "<mark>thermique</mark>", snippets('"therm"*', [part.pk])[part.pk]
        )
        phrase = snippets('"résistance thermique"', [part.pk])[part.pk]
        self.assertIn("<mark>résistance thermique</mark>", phrase)

    def test_terme_dans_le_titre(self):
        part = self.part("texte", heading_path="Alpha › Calibration")

        html = snippets('"calibration"', [part.pk])[part.pk]

        self.assertIn("<mark>Calibration</mark>", html)

    def test_plusieurs_note_parts_et_aucune(self):
        a = self.part("banc un")
        b = self.part("banc deux")
        self.part("autre chose")

        self.assertEqual(set(snippets('"banc"', [a.pk, b.pk])), {a.pk, b.pk})
        self.assertEqual(snippets('"banc"', []), {})

    def test_beaucoup_de_note_parts(self):
        parts = [self.part(f"banc {i}") for i in range(700)]

        self.assertEqual(len(snippets('"banc"', [p.pk for p in parts])), 700)


class GroupingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.old = Note.objects.create(date="2026-09-10")
        cls.new = Note.objects.create(date="2026-10-15")

    def part(self, note, content, heading_path=""):
        return NotePart.objects.create(
            note=note, project=self.project, content=content, heading_path=heading_path
        )

    def groups(self, text):
        query = parse_query(text)
        parts = search_note_parts(query)
        assert parts is not None
        return group_by_note(query, parts)

    def test_une_note_regroupe_ses_note_parts(self):
        a = self.part(self.new, "banc un")
        b = self.part(self.new, "banc deux")
        c = self.part(self.old, "banc trois")

        groups = self.groups("banc")

        self.assertEqual(len(groups), 2)
        by_note = {g.note: [h.part for h in g.hits] for g in groups}
        self.assertEqual(set(by_note[self.new]), {a, b})
        self.assertEqual(by_note[self.old], [c])

    def test_la_note_de_la_meilleure_note_part_vient_en_premier(self):
        self.part(self.new, "banc " + "autre " * 40)
        self.part(self.old, "banc")

        groups = self.groups("banc")

        self.assertEqual([g.note for g in groups], [self.old, self.new])

    def test_sans_texte_la_plus_recente_d_abord_sans_extrait(self):
        self.part(self.old, "x")
        self.part(self.new, "y")

        groups = self.groups("projet:alpha")

        self.assertEqual([g.note for g in groups], [self.new, self.old])
        self.assertIsNone(groups[0].hits[0].snippet)

    def test_extrait_present_avec_du_texte(self):
        self.part(self.new, "le banc est prêt")

        hit = self.groups("banc")[0].hits[0]

        self.assertIn("<mark>banc</mark>", hit.snippet)

    def test_resultat_elargi_a_son_extrait(self):
        self.part(self.new, "la thermique du banc")

        hit = self.groups("thermiqe")[0].hits[0]

        self.assertIn("<mark>thermique</mark>", hit.snippet)

    def test_exclusion_seule_sans_extrait(self):
        self.part(self.new, "le banc est prêt")
        self.part(self.new, "autre")

        hit = self.groups("-banc")[0].hits[0]

        self.assertIsNone(hit.snippet)

    def test_ancre_de_la_section(self):
        self.part(self.new, "banc", heading_path="Alpha › Réunion › Préparation")

        hit = self.groups("banc")[0].hits[0]

        self.assertEqual(hit.anchor, "préparation")

    def test_sans_titre_pas_d_ancre(self):
        self.part(self.new, "banc", heading_path="")

        self.assertIsNone(self.groups("banc")[0].hits[0].anchor)


class SearchPageGroupingTests(TestCase):
    url = reverse("note_taking:notes_search")

    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        cls.new = Note.objects.create(date="2026-10-15")
        cls.old = Note.objects.create(date="2026-09-10")
        for note, content, path in [
            (cls.new, "banc de mesure", "Alpha › Réunion"),
            (cls.new, "banc de test", "Alpha › Bilan"),
            (cls.old, "un banc", "Alpha"),
        ]:
            NotePart.objects.create(
                note=note, project=cls.project, content=content, heading_path=path
            )

    def test_un_titre_par_note(self):
        response = self.client.get(self.url, {"q": "banc"})
        html = response.content.decode()

        self.assertEqual(html.count("15 octobre 2026</time>"), 1)
        self.assertEqual(html.count("10 septembre 2026</time>"), 1)

    def test_extraits_surlignes(self):
        response = self.client.get(self.url, {"q": "banc"})

        self.assertContains(response, "<mark>banc</mark>")

    def test_lien_vers_la_section(self):
        response = self.client.get(self.url, {"q": "mesure"})
        note_url = reverse("note_taking:note_detail", args=["2026-10-15"])

        self.assertContains(response, f'href="{note_url}#réunion"')

    def test_lien_vers_la_note_sans_titre(self):
        response = self.client.get(self.url, {"q": "un banc"})
        note_url = reverse("note_taking:note_detail", args=["2026-09-10"])

        self.assertContains(response, f'href="{note_url}"')

    def test_nombre_de_resultats(self):
        response = self.client.get(self.url, {"q": "banc"})

        self.assertContains(response, "3 résultats dans 2 notes")

    def test_un_seul_resultat(self):
        response = self.client.get(self.url, {"q": "mesure"})

        self.assertContains(response, "1 résultat dans 1 note.")

    def test_sans_texte_le_contenu_rendu(self):
        response = self.client.get(self.url, {"q": "projet:alpha"})

        self.assertContains(response, "<p>banc de mesure</p>")
        self.assertNotContains(response, "<mark>")

    def test_hierarchie_des_titres(self):
        response = self.client.get(self.url, {"q": "banc"}, HTTP_HX_REQUEST="true")
        html = response.content.decode()

        # h1 de la page, h2 par note, h3 par résultat.
        self.assertIn("<h2", html)
        self.assertIn("<h3", html)
        self.assertNotIn("<h1", html)
