"""Trier les résultats par pertinence ou par date (#430)."""

from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Project
from note_taking import search
from note_taking.models import Note, Passage


class ResultSortTests(SimpleTestCase):
    """Le tri lu dans l'adresse ; `with_relevance` : la pertinence est possible."""

    def test_defaut(self):
        self.assertEqual(search.result_sort({}, with_relevance=True), "relevance")
        self.assertEqual(search.result_sort({}, with_relevance=False), "newest")

    def test_tri_choisi(self):
        for sort in ("newest", "oldest"):
            for possible in (True, False):
                with self.subTest(sort=sort, with_relevance=possible):
                    self.assertEqual(
                        search.result_sort({"sort": sort}, with_relevance=possible),
                        sort,
                    )

    def test_pertinence_impossible_ou_valeur_inconnue(self):
        self.assertEqual(
            search.result_sort({"sort": "relevance"}, with_relevance=False), "newest"
        )
        self.assertEqual(
            search.result_sort({"sort": "x"}, with_relevance=True), "relevance"
        )
        self.assertEqual(
            search.result_sort({"sort": "x"}, with_relevance=False), "newest"
        )


class SortedPageTestCase(TestCase):
    url = reverse("note_taking:notes_search")

    @classmethod
    def setUpTestData(cls):
        cls.project = Project.objects.create(name="Alpha")
        for day in ("2026-09-10", "2026-10-15", "2026-11-02"):
            note = Note.objects.create(date=day)
            # Le plus pertinent (le mot seul) est le deuxième passage de chaque note,
            # et la note d'octobre a le plus pertinent de tous.
            cls.part(note, 0, f"premier {day} banc " + "texte " * 20)
            repeated = "banc " * (9 if day == "2026-10-15" else 2)
            cls.part(note, 1, f"second {day} {repeated}")

    @classmethod
    def part(cls, note, position, content):
        return Passage.objects.create(
            note=note,
            project=cls.project,
            content=content,
            heading_path="Alpha",
            position=position,
        )

    def get(self, q="banc", **params):
        return self.client.get(self.url, {"q": q, **params})

    def order(self, response) -> list[tuple[str, str]]:
        """Les passages affichés (vue extraits) : date de la note, premier mot."""
        return [
            (hit.passage.note.date.isoformat()[:7], hit.passage.content.split()[0])
            for group in response.context["groups"]
            for hit in group.hits
        ]

    def months(self, response) -> list[str]:
        return list(dict.fromkeys(month for month, _ in self.order(response)))


NEWEST = ["2026-11", "2026-10", "2026-09"]


def written(months: list[str]) -> list[tuple[str, str]]:
    """Chaque note dans l'ordre où elle est écrite."""
    return [(month, word) for month in months for word in ("premier", "second")]


class ExtractsSortTests(SortedPageTestCase):
    def test_avec_des_mots_la_pertinence_par_defaut(self):
        response = self.get()

        self.assertEqual(self.order(response)[0], ("2026-10", "second"))
        self.assertEqual(self.order(self.get(sort="relevance")), self.order(response))
        self.assertEqual(self.order(self.get(sort="x")), self.order(response))

    def test_avec_des_mots_par_date_chaque_note_telle_qu_ecrite(self):
        self.assertEqual(self.order(self.get(sort="newest")), written(NEWEST))
        self.assertEqual(self.order(self.get(sort="oldest")), written(NEWEST[::-1]))

    def test_filtres_seuls(self):
        self.assertEqual(self.order(self.get("projet:Alpha")), written(NEWEST))
        self.assertEqual(
            self.order(self.get("projet:Alpha", sort="relevance")), written(NEWEST)
        )
        self.assertEqual(
            self.order(self.get("projet:Alpha", sort="oldest")),
            written(NEWEST[::-1]),
        )

    def test_mot_exclu_seul_comme_des_filtres(self):
        self.assertEqual(self.order(self.get("-absent")), written(NEWEST))


class DocumentSortTests(SortedPageTestCase):
    def dates(self, response) -> list[int]:
        """Les mois des notes, dans l'ordre du document."""
        html = response.content.decode()
        html = html[html.index("rendered-content") :]
        places = {
            month: html.index(f"/notes/{day}/")
            for month, day in (
                (9, "2026-09-10"),
                (10, "2026-10-15"),
                (11, "2026-11-02"),
            )
        }
        return sorted(places, key=lambda month: places[month])

    def test_le_tri_choisit_le_sens_des_dates(self):
        for group in ("date", "path"):
            with self.subTest(group=group):
                options = {"view": "document", "group": group}
                self.assertEqual(self.dates(self.get(**options)), [11, 10, 9])
                self.assertEqual(
                    self.dates(self.get(sort="relevance", **options)), [11, 10, 9]
                )
                self.assertEqual(
                    self.dates(self.get(sort="oldest", **options)), [9, 10, 11]
                )

    def test_les_passages_d_une_note_restent_dans_l_ordre_ecrit(self):
        for sort in ("newest", "oldest"):
            with self.subTest(sort=sort):
                html = self.get(view="document", sort=sort).content.decode()
                self.assertLess(
                    html.index("premier 2026-10-15"), html.index("second 2026-10-15")
                )


class SortSelectorTests(SortedPageTestCase):
    WHY = "La pertinence demande des mots cherchés"

    def test_les_tris_gardent_le_reste_de_l_adresse(self):
        response = self.get(projects=self.project.pk)

        for sort in ("relevance", "newest", "oldest"):
            self.assertContains(
                response,
                f'href="{self.url}?q=banc&amp;projects={self.project.pk}&amp;sort={sort}"',
            )

    def test_tri_courant_marque(self):
        for params, label in (
            ({}, "Pertinence"),
            ({"sort": "oldest"}, "Plus anciennes d'abord"),
        ):
            with self.subTest(params=params):
                html = self.get(**params).content.decode()
                self.assertRegex(html, rf'aria-current="true"[^>]*>{label}</a>')

    def test_pertinence_grisee_sans_mot(self):
        response = self.get("projet:Alpha")

        self.assertContains(response, 'aria-disabled="true"', count=1)
        self.assertContains(response, self.WHY)
        self.assertNotContains(response, "sort=relevance")

    def test_pertinence_pas_proposee_dans_un_document(self):
        response = self.get(view="document")

        self.assertNotContains(response, "Pertinence")
        self.assertNotContains(response, "sort=relevance")
        self.assertContains(response, "sort=oldest")

    def test_le_tri_choisi_survit_a_une_nouvelle_recherche(self):
        hidden = '<input type="hidden" name="sort" value="{}">'

        self.assertContains(self.get(sort="oldest"), hidden.format("oldest"), html=True)
        # Gardé même quand il ne s'applique pas : des mots peuvent revenir.
        self.assertContains(
            self.get("projet:Alpha", sort="relevance"),
            hidden.format("relevance"),
            html=True,
        )
        self.assertNotContains(self.get(), 'name="sort"')
        self.assertNotContains(self.get(sort="x"), 'name="sort"')


class AssembledOrderTests(SimpleTestCase):
    def test_assemblage_du_plus_ancien_au_plus_recent(self):
        from note_taking.search_document import DocPassage, Level, assemble

        pieces = [
            DocPassage(
                date=date(2026, 10, day),
                date_label=f"{day} octobre",
                note_url=f"/notes/2026-10-{day}/",
                passage_url=f"/notes/2026-10-{day}/#a",
                levels=(Level(1, "Alpha"),),
                content=f"texte {day} {word}",
            )
            for day in (11, 12)
            for word in ("un", "deux")
        ]
        for group in ("date", "path"):
            with self.subTest(group=group):
                text = assemble(pieces, group, oldest_first=True)
                places = [
                    text.index(f"texte {day} {word}")
                    for day in (11, 12)
                    for word in ("un", "deux")
                ]
                self.assertEqual(places, sorted(places))
