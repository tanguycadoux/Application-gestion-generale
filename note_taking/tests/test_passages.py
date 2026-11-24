"""Les passages d'une note (#387) : une section telle qu'écrite, à sa place.

Un passage est le texte entre un titre et le suivant (ou depuis le début de la
note), dans l'ordre, avec ses lignes et l'identifiant de son titre dans la page de
la note. Un titre répété donne deux passages. Le texte avant le premier `#` est un
passage sans projet (#385) : indexé, cherchable, ses images liées, et signalé à
l'enregistrement.
"""

import shutil
import tempfile

from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import Project
from images.services import import_image
from images.tests.files import image_file
from note_taking.models import Note, Passage
from note_taking.qmd.parser import parse_note
from note_taking.search import document_layout, group_by_note, search_passages
from note_taking.search_query import parse_query
from note_taking.services import process_passages

MEDIA_ROOT = tempfile.mkdtemp()

REPEATED = "# A\nun\n# B\ndeux\n# A\ntrois"


def passages(raw: str):
    return parse_note("2026-11-22", raw).passages


class ParsedPassageTests(SimpleTestCase):
    def test_un_titre_repete_donne_deux_passages_dans_l_ordre(self):
        found = passages(REPEATED)

        self.assertEqual(
            [(p.project, p.lines) for p in found],
            [("A", ["un"]), ("B", ["deux"]), ("A", ["trois"])],
        )

    def test_lignes_de_debut_et_de_fin(self):
        """Du titre (compris) à la ligne avant le titre suivant, ou à la fin."""
        found = passages("# A\nun\n\n## B\ndeux\n# C\ntrois\n")

        self.assertEqual(
            [(p.start_line, p.end_line) for p in found], [(1, 3), (4, 5), (6, 8)]
        )

    def test_un_titre_sans_texte_n_a_pas_de_passage(self):
        found = passages("# A\n## B\ntexte")

        self.assertEqual([p.headings for p in found], [["A", "B"]])
        self.assertEqual((found[0].start_line, found[0].end_line), (2, 3))

    def test_texte_avant_le_premier_titre(self):
        found = passages("note rapide\n- [ ] appeler\n# P\nx")

        self.assertEqual(
            [(p.project, p.path, p.headings, p.lines) for p in found],
            [
                (None, [], [], ["note rapide", "- [ ] appeler"]),
                ("P", [], ["P"], ["x"]),
            ],
        )
        self.assertEqual((found[0].start_line, found[0].end_line), (1, 2))

    def test_sous_titre_sans_projet(self):
        found = passages("## S\nx\n# P\ny")

        self.assertEqual(
            [(p.project, p.path, p.headings) for p in found],
            [(None, ["S"], ["S"]), ("P", [], ["P"])],
        )

    def test_tags_d_un_bloc_metadata_gardent_leur_portee(self):
        raw = "# P\n::: {.metadata}\ntags: [a]\n:::\nun\n## S\ndeux\n# Q\ntrois"

        self.assertEqual(
            [(p.lines, sorted(p.tags)) for p in passages(raw)],
            [(["un"], ["a"]), (["deux"], ["a"]), (["trois"], [])],
        )


class ProjectlessWarningTests(SimpleTestCase):
    def warnings(self, raw: str) -> list[str]:
        return parse_note("2026-11-22", raw).warnings

    def test_texte_sans_projet_signale(self):
        self.assertEqual(
            self.warnings("note rapide\n\n- [ ] appeler\n# P\nx"),
            [
                "2 lignes sans projet, avant le premier titre « # » : à ranger "
                "sous un projet."
            ],
        )

    def test_une_ligne(self):
        self.assertEqual(
            self.warnings("intro\n# P\nx"),
            [
                "1 ligne sans projet, avant le premier titre « # » : à ranger sous un projet."
            ],
        )

    def test_rien_sans_texte_avant_le_projet(self):
        self.assertEqual(self.warnings("\n\n# P\nx"), [])

    def test_avant_les_titres_a_verifier(self):
        """Le rappel vient en premier : le toast ne dit que le premier."""
        found = self.warnings("intro\n# A\n### B\nx")

        self.assertEqual(len(found), 2)
        self.assertIn("sans projet", found[0])
        self.assertIn("saute un niveau", found[1])


class StoredPassageTests(TestCase):
    def process(self, body: str, day: str = "2026-11-22") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def stored(self, note: Note):
        return list(note.passages.order_by("position"))

    def test_position_lignes_et_identifiants_des_titres_repetes(self):
        note = self.process(REPEATED)

        self.assertEqual(
            [
                (p.position, p.project.name, p.start_line, p.end_line, p.heading_id)
                for p in self.stored(note)
            ],
            [(0, "A", 1, 2, "a"), (1, "B", 3, 4, "b"), (2, "A", 5, 6, "a-1")],
        )

    def test_identifiants_de_tout_le_chemin(self):
        note = self.process("# P\n## x\nun\n# Q\ntexte\n# P\n## x\ndeux")

        self.assertEqual(
            [(p.heading_path, p.anchor_path) for p in self.stored(note)],
            [("P › x", "p x"), ("Q", "q"), ("P › x", "p-1 x-1")],
        )

    def test_identifiants_comme_la_page_de_la_note(self):
        """Ceux de `add_heading_ids` sur la note rendue : le titre d'un encadré en
        est le titre, sans identifiant ; celui d'une citation en prend un."""
        body = (
            "# P\n::: {.callout-note}\n## Suivi\n:::\n## Suivi\nun\n"
            "> ## Bilan\n\n## Bilan\ndeux"
        )
        note = self.process(body)

        page = self.client.get(reverse("note_taking:note_detail", args=[note.date]))

        anchors = [p.heading_id for p in self.stored(note)]
        self.assertEqual(anchors, ["p", "suivi", "bilan-1"])
        for anchor in anchors:
            self.assertContains(page, f'id="{anchor}"')

    def test_identifiant_explicite(self):
        note = self.process("# P\n## Suivi {#mon-suivi}\ntexte")

        self.assertEqual(self.stored(note)[-1].heading_id, "mon-suivi")

    def test_passage_sans_projet(self):
        note = self.process("note rapide\n# P\nx")

        first = self.stored(note)[0]
        self.assertIsNone(first.project)
        self.assertIsNone(first.section)
        self.assertEqual((first.heading_id, first.heading_path), ("", ""))
        self.assertEqual(first.content, "note rapide")

    def test_un_projet_sans_passage_n_est_pas_cree(self):
        self.process("note rapide")

        self.assertFalse(Project.objects.exists())

    def test_projets_de_la_note_sans_le_texte_sans_projet(self):
        note = self.process("intro\n# P\nx")

        self.assertEqual([p.name for p in note.projects], ["P"])

    def test_avertissement_a_l_enregistrement(self):
        response = self.client.post(
            reverse("note_taking:new_note"),
            {"date": "2026-11-22", "body": "intro\n# P\nx"},
            follow=True,
        )

        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("1 ligne sans projet" in text for text in texts), texts)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ProjectlessImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_images_du_texte_sans_projet_liees(self):
        image = import_image(image_file("schema.png"))
        note = Note.objects.create(
            date="2026-11-22", body="![](images/schema.png)\n# P\nx"
        )

        process_passages(note)

        self.assertEqual(list(note.images), [image])
        self.assertEqual(list(note.passages.get(project=None).images.all()), [image])


class PassageSearchTests(TestCase):
    def process(self, body: str, day: str = "2026-11-22") -> Note:
        note = Note.objects.create(date=day, body=body)
        process_passages(note)
        return note

    def search(self, text: str):
        return search_passages(parse_query(text)) or []

    def test_texte_sans_projet_cherchable(self):
        self.process("idée de capteur\n# P\nautre chose")

        found = self.search("capteur")

        self.assertEqual([p.project for p in found], [None])

    def test_ancre_exacte_d_un_titre_repete(self):
        self.process("# A\n## Suivi\nrien\n# B\nx\n# A\n## Suivi\naiguille")

        query = parse_query("aiguille")
        hit = group_by_note(query, search_passages(query) or [])[0].hits[0]

        self.assertEqual(hit.anchor, "suivi-1")
        self.assertEqual([crumb.anchor for crumb in hit.crumbs], ["a-1", "suivi-1"])

    def test_chaque_occurrence_a_son_ancre(self):
        note = self.process("# A\nmot un\n# B\nx\n# A\nmot deux")

        response = self.client.get(reverse("note_taking:notes_search"), {"q": "mot"})

        url = reverse("note_taking:note_detail", args=[note.date])
        self.assertContains(response, f'href="{url}#a"')
        self.assertContains(response, f'href="{url}#a-1"')

    def test_document_dans_l_ordre_de_la_note(self):
        """Le dernier passage écrit vient en dernier, même s'il a le même chemin
        qu'un passage plus haut."""
        self.process("# A\nmot premier\n# B\nmot milieu\n# A\nmot dernier")

        html = document_layout(self.search("mot"), "date").html

        self.assertLess(html.index("premier"), html.index("milieu"))
        self.assertLess(html.index("milieu"), html.index("dernier"))

    def test_document_texte_sans_projet(self):
        self.process("mot libre\n# P\nmot rangé")

        html = document_layout(self.search("mot"), "date").html

        self.assertIn("Sans projet", html)
        self.assertLess(html.index("libre"), html.index("rangé"))

    def test_compteur_en_passages(self):
        self.process("# A\nmot un\n# B\nx\n# A\nmot deux")

        response = self.client.get(reverse("note_taking:notes_search"), {"q": "mot"})

        self.assertContains(response, "2 passages dans 1 note.")

    def test_resultat_sans_projet_mene_au_debut_de_la_note(self):
        note = self.process("mot libre\n# P\nx")

        response = self.client.get(reverse("note_taking:notes_search"), {"q": "libre"})

        url = reverse("note_taking:note_detail", args=[note.date])
        self.assertContains(response, f'<a href="{url}">Début de la note</a>')


class PassageModelTests(TestCase):
    def test_str_sans_projet(self):
        note = Note.objects.create(date="2026-11-22")

        self.assertEqual(str(Passage.objects.create(note=note)), "Sans projet")


class QuotedHeadingTests(TestCase):
    def test_titre_d_une_citation_avant_le_sien(self):
        """Un titre dans une citation prend un identifiant sans être un titre de
        la note : le titre qui le suit est le `-1`."""
        note = Note.objects.create(
            date="2026-11-22", body="# P\n> ## Suivi\n\n## Suivi\ntexte"
        )
        process_passages(note)

        self.assertEqual(note.passages.last().heading_id, "suivi-1")
