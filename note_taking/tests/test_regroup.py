"""Regrouper les titres répétés d'une note (#315)."""

from collections import Counter

from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from note_taking.exceptions import RegroupError
from note_taking.models import Note
from note_taking.qmd.parser import parse_note
from note_taking.qmd.regroup import (
    BLOCKED_LIST,
    BLOCKED_METADATA,
    regroup_headings,
    repeated_headings,
)
from note_taking.services import process_passages


def regroup_all(body: str) -> str:
    keys = {heading.key for heading in repeated_headings(body) if not heading.blocked}
    return regroup_headings(body, keys)


class RepeatedHeadingsTests(SimpleTestCase):
    def test_projet_repete(self):
        [heading] = repeated_headings("# A\na\n# B\nb\n# A\nc")

        self.assertEqual(heading.written, "# A")
        self.assertEqual(heading.key, "1")
        self.assertEqual([o.line for o in heading.occurrences], [1, 5])
        self.assertEqual(heading.blocked, "")

    def test_sous_titre_repete_sous_le_meme_parent(self):
        [heading] = repeated_headings("# A\n## x\n1\n## y\n## x\n2")

        self.assertEqual(heading.chain, "A › x")
        self.assertEqual([o.line for o in heading.occurrences], [2, 5])

    def test_meme_titre_sous_deux_parents_n_est_pas_repete(self):
        self.assertEqual(repeated_headings("# A\n## x\n# B\n## x"), [])

    def test_casse_attributs_ou_niveau_differents_pas_regroupes(self):
        # Le chemin des tâches garde les titres tels qu'écrits (#240).
        body = "# P\n## a\n## A\n## a {#x}\n### a"

        self.assertEqual(repeated_headings(body), [])

    def test_titres_d_un_bloc_de_code_ou_d_un_callout_ignores(self):
        body = "# A\n```\n# A\n```\n::: {.callout-note}\n# A\n:::"

        self.assertEqual(repeated_headings(body), [])

    def test_sous_titres_entraines(self):
        [heading] = repeated_headings("# A\n## x\n1\n# A\n## x\n2\n## y")

        self.assertEqual(heading.nested, ["x"])

    def test_texte_qui_ne_s_analyse_pas(self):
        self.assertEqual(repeated_headings("# A\n::: {.metadata}\nmal\n:::\n# A"), [])


class RegroupTests(SimpleTestCase):
    def test_texte_avant_les_sous_titres_et_fusion_recursive(self):
        body = "# A\na1\n\n## x\nx1\n\n# B\nb1\n\n# A\na2\n\n## x\nx2\n\n## y\ny2\n"

        self.assertEqual(
            regroup_all(body),
            "# A\na1\n\na2\n\n## x\nx1\n\nx2\n\n## y\ny2\n\n# B\nb1\n",
        )

    def test_titre_sans_texte(self):
        self.assertEqual(regroup_all("# A\n## x\n# A\na"), "# A\na\n\n## x")

    def test_ligne_vide_avant_un_titre_qui_suivait_autre_chose(self):
        # `y` suivait la fin de la note : il rejoint `A`, avant `# B`.
        self.assertEqual(
            regroup_all("# A\n## x\n1\n# B\nb\n# A\n## y\n2"),
            "# A\n## x\n1\n\n## y\n2\n\n# B\nb",
        )

    def test_debut_de_la_note_et_fin_de_ligne_gardes(self):
        body = "---\ntitle: x\n---\nsans projet\n\n# A\na\n\n# A\nb\n\n\n"

        self.assertEqual(
            regroup_all(body), "---\ntitle: x\n---\nsans projet\n\n# A\na\n\nb\n\n\n"
        )

    def test_fins_de_ligne_windows(self):
        self.assertEqual(
            regroup_all("# A\r\na\r\n# B\r\nb\r\n# A\r\nc\r\n"),
            "# A\r\na\r\n\r\nc\r\n\r\n# B\r\nb\r\n",
        )

    def test_seuls_les_titres_choisis(self):
        body = "# A\n# B\n# A\n# B"
        keys = {heading.key for heading in repeated_headings(body)}

        self.assertEqual(keys, {"1", "2"})
        self.assertEqual(regroup_headings(body, {"1"}), "# A\n# B\n\n# B")

    def test_les_chemins_ne_changent_pas(self):
        body = "# A\n- a\n## x\n- b\n# B\n- c\n# A\n- d\n## x\n- e\n### z\n- f"

        def lines(text: str) -> Counter:
            return Counter(
                (tuple(passage.headings), line)
                for passage in parse_note("", text).passages
                for line in passage.lines
                if line
            )

        self.assertEqual(lines(regroup_all(body)), lines(body))
        self.assertEqual(repeated_headings(regroup_all(body)), [])

    def test_titre_choisi_qui_n_est_plus_repete(self):
        with self.assertRaises(RegroupError):
            regroup_headings("# A\n# B", {"1"})


class BlockedRegroupTests(SimpleTestCase):
    def test_bloc_de_metadonnees_qui_vaudrait_pour_un_autre_texte(self):
        # Les tags du premier `A` vaudraient pour le texte du second.
        body = "# A\n::: {.metadata}\ntags: [k]\n:::\na\n\n# A\nb"
        [heading] = repeated_headings(body)

        self.assertEqual(heading.blocked, BLOCKED_METADATA)
        with self.assertRaises(RegroupError):
            regroup_headings(body, {heading.key})

    def test_bloc_de_metadonnees_qui_garde_sa_portee(self):
        # Écrit après du texte, le bloc ne vaut que pour la suite : rien ne change.
        body = "# A\na\n\n# A\n::: {.metadata}\ntags: [k]\n:::\nb"
        [heading] = repeated_headings(body)

        self.assertEqual(heading.blocked, "")

    def test_branche_todo(self):
        body = "# A\n- a\n## x\n::: {.metadata}\ntodo: true\n:::\n- b\n# A\n- c"
        [heading] = repeated_headings(body)

        self.assertEqual(heading.blocked, "")
        self.assertIn("- a\n\n- c\n\n## x", regroup_all(body))

    def test_texte_deplace_en_retrait(self):
        body = "# A\n- [ ] t\n\n# A\n  - [ ] u"
        [heading] = repeated_headings(body)

        self.assertEqual(heading.blocked, BLOCKED_LIST)

    def test_texte_en_retrait_sous_un_titre_sans_texte(self):
        [heading] = repeated_headings("# A\n# A\n  - [ ] u")

        self.assertEqual(heading.blocked, "")


class RegroupViewTests(TestCase):
    BODY = "# A\na\n\n# B\nb\n\n# A\nc\n"

    def setUp(self):
        self.note = Note.objects.create(date="2026-11-26", body=self.BODY)
        process_passages(self.note)
        self.url = reverse("note_taking:regroup_review", args=["2026-11-26"])

    def post(self, **data):
        self.note.refresh_from_db()
        data.setdefault("version", self.note.updated.isoformat())
        return self.client.post(self.url, data)

    def test_apercu(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'name="headings" value="1"')
        self.assertContains(response, "Lignes 7 à 8")
        self.assertContains(response, "# A\na\n\nc\n\n# B\nb")

    def test_titre_non_propose_decoche_et_desactive(self):
        self.note.body = "# A\n::: {.metadata}\ntags: [k]\n:::\na\n# A\nb"
        self.note.save()

        response = self.client.get(self.url)

        self.assertContains(response, " disabled>")
        self.assertContains(response, "Aucun de ces titres")

    def test_regroupement(self):
        response = self.post(headings=["1"])

        self.note.refresh_from_db()
        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[self.note.date])
        )
        self.assertEqual(self.note.body, "# A\na\n\nc\n\n# B\nb\n")
        self.assertEqual(self.note.updated_by, Note.Source.REGROUP)
        self.assertEqual(self.note.passages.count(), 2)

    def test_note_changee_depuis_l_apercu(self):
        response = self.post(headings=["1"], version="2000-01-01T00:00:00+00:00")

        self.note.refresh_from_db()
        self.assertRedirects(response, self.url)
        self.assertEqual(self.note.body, self.BODY)

    def test_rien_de_coche(self):
        self.post()

        self.note.refresh_from_db()
        self.assertEqual(self.note.body, self.BODY)

    def test_sans_titre_repete(self):
        self.note.body = "# A"
        self.note.save()

        response = self.client.get(self.url)

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[self.note.date])
        )


class RegroupProposalTests(TestCase):
    def test_page_de_la_note(self):
        Note.objects.create(date="2026-11-26", body="# A\n# A")

        response = self.client.get(
            reverse("note_taking:note_detail", args=["2026-11-26"])
        )

        self.assertContains(response, "Regrouper les titres répétés")
        self.assertContains(
            response, reverse("note_taking:regroup_review", args=["2026-11-26"])
        )

    def test_pas_de_proposition_sans_titre_repete(self):
        Note.objects.create(date="2026-11-26", body="# A\n# B")

        response = self.client.get(
            reverse("note_taking:note_detail", args=["2026-11-26"])
        )

        self.assertNotContains(response, "Regrouper les titres répétés")

    def test_enregistrement_garde_le_texte_et_le_signale(self):
        note = Note.objects.create(date="2026-11-26", body="# A")
        response = self.client.post(
            reverse("note_taking:edit_note", args=["2026-11-26"]),
            {"date": "2026-11-26", "body": "# A\na\n# B\n# A\nb"},
        )

        note.refresh_from_db()
        self.assertEqual(note.body, "# A\na\n# B\n# A\nb")
        texts = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("« A »" in text and "proposé" in text for text in texts))
