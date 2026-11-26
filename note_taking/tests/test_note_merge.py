"""Fusion automatique quand les modifications ne se recouvrent pas (#472).

Le texte ouvert par l'éditeur (`original`), le texte saisi et la version enregistrée
entre-temps sont comparés ligne à ligne. Deux modifications qui touchent les mêmes
lignes, ou des lignes voisines, sont un conflit : l'encadré de #468 reste.
"""

import json
import logging
import random
import re
from collections import Counter

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from note_taking.models import Note
from note_taking.services import process_passages
from note_taking.text_merge import apply_edits, merge_texts
from todolist.models import Task


class MergeTextsTests(SimpleTestCase):
    ORIGINAL = "# A\na\n\n# B\nb"

    def test_capture_en_fin_de_section_pendant_une_modification_ailleurs(self):
        merge = merge_texts(
            self.ORIGINAL, "# A\na modifié\n\n# B\nb", self.ORIGINAL + "\n- capture"
        )

        assert merge is not None
        self.assertEqual(merge.text, "# A\na modifié\n\n# B\nb\n- capture")
        self.assertEqual(merge.edits, [{"from": 5, "to": 5, "lines": ["- capture"]}])

    def test_deux_ajouts_au_meme_endroit(self):
        self.assertIsNone(
            merge_texts(
                self.ORIGINAL, self.ORIGINAL + "\nmien", self.ORIGINAL + "\nautre"
            )
        )

    def test_ligne_supprimee_modifiee_de_l_autre_cote(self):
        self.assertIsNone(
            merge_texts(self.ORIGINAL, "# A\n\n# B\nb", "# A\na changé\n\n# B\nb")
        )

    def test_lignes_voisines(self):
        self.assertIsNone(
            merge_texts(self.ORIGINAL, "# A\na2\n\n# B\nb", "# A\na\nx\n# B\nb")
        )

    def test_memes_modifications_des_deux_cotes(self):
        """Prudent : deux fois la même ligne ajoutée n'est pas tranché ici."""
        self.assertIsNone(
            merge_texts(self.ORIGINAL, self.ORIGINAL + "\nx", self.ORIGINAL + "\nx")
        )

    def test_rien_n_a_change_ailleurs(self):
        merge = merge_texts(self.ORIGINAL, "# A\nz\n\n# B\nb", self.ORIGINAL)

        assert merge is not None
        self.assertEqual(merge.text, "# A\nz\n\n# B\nb")
        self.assertEqual(merge.edits, [])

    def test_rien_n_a_change_dans_l_editeur(self):
        saved = "# A\na\n\n# B\nb\nc"
        merge = merge_texts(self.ORIGINAL, self.ORIGINAL, saved)

        assert merge is not None
        self.assertEqual(merge.text, saved)

    def test_fins_de_ligne_windows(self):
        """La page envoie des CRLF ; la base a ceux du dernier enregistrement."""
        merge = merge_texts(
            "# A\na\n\n# B\nb",
            "# A\r\na modifié\r\n\r\n# B\r\nb",
            "# A\r\na\r\n\r\n# B\r\nb\r\n- capture",
        )

        assert merge is not None
        self.assertEqual(merge.text, "# A\r\na modifié\r\n\r\n# B\r\nb\r\n- capture")
        self.assertEqual(merge.edits, [{"from": 5, "to": 5, "lines": ["- capture"]}])

    def test_retour_a_la_ligne_final(self):
        merge = merge_texts(
            "# A\na\n\n# B\nb\n", "# A\nz\n\n# B\nb\n", "# A\na\n\n# B\nb\nc\n"
        )

        assert merge is not None
        self.assertEqual(merge.text, "# A\nz\n\n# B\nb\nc\n")

    def test_modifications_aleatoires_aucune_ligne_perdue(self):
        """Ce qui est fusionné est le texte saisi, plus ce que la version enregistrée
        ajoute, moins ce qu'elle retire : rien d'autre. Sur des lignes toutes
        différentes, le résultat est exactement celui des deux modifications."""
        rng = random.Random(472)
        merged = 0
        for _ in range(600):
            distinct = rng.random() < 0.5
            size = rng.randint(4, 16)
            if distinct:
                base = [f"l{i}" for i in range(size)]
            else:
                base = [
                    rng.choice(["", "a", "b", "- [ ] t", "# A"]) for _ in range(size)
                ]
            cut = rng.randint(1, size - 2)
            mine, mine_new = self.edit(rng, base, 0, cut, "m")
            theirs, theirs_new = self.edit(rng, base, cut + 1, size, "t")
            merge = merge_texts("\n".join(base), "\n".join(mine), "\n".join(theirs))
            if merge is None:
                continue
            merged += 1
            result = merge.text.split("\n")
            self.assertEqual(
                Counter(result), Counter(mine) + Counter(theirs) - Counter(base)
            )
            self.assertEqual(apply_edits("\n".join(mine), merge.edits), merge.text)
            self.assertTrue(set(result) <= set(mine) | set(theirs))
            if distinct:
                expected = mine_new[: len(mine_new) - (size - cut)] + theirs_new[cut:]
                self.assertEqual(result, expected)
        self.assertGreater(merged, 300)

    @staticmethod
    def edit(rng, base, low, high, mark):
        """`base` modifié entre les lignes `low` et `high` : une ligne remplacée,
        ajoutée ou retirée."""
        lines = list(base)
        position = rng.randint(low, high - 1)
        action = rng.choice(["replace", "insert", "delete"])
        if action == "replace":
            lines[position] = f"{mark}{rng.randint(0, 9)}"
        elif action == "insert":
            lines.insert(position, f"{mark}+{rng.randint(0, 9)}")
        else:
            del lines[position]
        return lines, lines


class MergeViewTests(TestCase):
    ORIGINAL = "# A\na\n\n# B\nb"

    def setUp(self):
        self.day = str(timezone.localdate())
        self.note = Note.objects.create(date=self.day, body=self.ORIGINAL)
        process_passages(self.note)
        self.url = reverse("note_taking:edit_note", args=[self.day])
        html = self.client.get(self.url).content.decode()
        self.opened = re.search(r'name="version" value="([^"]+)"', html)[1]

    def elsewhere(self, body: str) -> None:
        """La capture rapide écrit pendant que l'éditeur est ouvert."""
        note = Note.objects.get()
        note.body = body
        note.save(source=Note.Source.CAPTURE)
        process_passages(note)

    def save(self, body: str, in_place: bool = False, **fields):
        data = {
            "date": self.day,
            "body": body,
            "version": self.opened,
            "original": self.ORIGINAL,
            **fields,
        }
        headers = {"HX-Request": "true"} if in_place else {}
        if in_place:
            data["stay"] = "1"
        return self.client.post(self.url, data, headers=headers)

    def test_fusion_enregistree_et_signalee(self):
        self.elsewhere(self.ORIGINAL + "\n- [ ] capturée")

        with self.assertLogs("note_taking", logging.INFO) as logs:
            response = self.save("# A\na\n- [ ] mienne\n\n# B\nb")

        self.assertEqual(response.status_code, 302)
        note = Note.objects.get()
        self.assertEqual(note.body, "# A\na\n- [ ] mienne\n\n# B\nb\n- [ ] capturée")
        self.assertEqual(note.updated_by, Note.Source.MERGE)
        self.assertTrue(any("fusion" in record.getMessage() for record in logs.records))
        page = self.client.get(response.url).content.decode()
        self.assertIn("par la capture rapide", page)
        self.assertIn("réunies", page)
        # Les tâches des deux côtés.
        self.assertEqual(
            set(Task.objects.values_list("title", flat=True)), {"mienne", "capturée"}
        )

    def test_sur_place_l_editeur_repart_de_la_version_fusionnee(self):
        self.elsewhere(self.ORIGINAL + "\n- capture")

        response = self.save("# A\nz\n\n# B\nb", in_place=True)

        self.assertEqual(response.status_code, 200)
        note = Note.objects.get()
        self.assertEqual(note.body, "# A\nz\n\n# B\nb\n- capture")
        self.assertEqual(response.headers["X-Note-Version"], note.updated.isoformat())
        html = response.content.decode()
        self.assertIn("data-toast", html)
        found = re.search(
            r'<script id="note-merge" type="application/json">(.*?)</script>', html
        )
        assert found is not None
        merge = json.loads(found[1])
        self.assertEqual(merge["text"], "# A\nz\n\n# B\nb\n- capture")
        self.assertEqual(merge["edits"], [{"from": 5, "to": 5, "lines": ["- capture"]}])

        # L'enregistrement suivant part de la version fusionnée.
        again = self.save(
            merge["text"] + "\nsuite",
            in_place=True,
            version=response.headers["X-Note-Version"],
            original=merge["text"],
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(Note.objects.get().body, "# A\nz\n\n# B\nb\n- capture\nsuite")

    def test_texte_echappe_dans_la_reponse(self):
        self.elsewhere(self.ORIGINAL + "\n</script><b>x</b>")

        html = self.save("# A\nz\n\n# B\nb", in_place=True).content.decode()

        self.assertNotIn("</script><b>", html)

    def test_recouvrement_conflit(self):
        self.elsewhere(self.ORIGINAL + "\nautre")

        response = self.save(self.ORIGINAL + "\nmien")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Note.objects.get().body, self.ORIGINAL + "\nautre")
        self.assertIn("1 ligne ajoutée", response.content.decode())

    def test_sans_texte_d_origine_conflit(self):
        self.elsewhere(self.ORIGINAL + "\n- capture")

        response = self.client.post(
            self.url,
            {"date": self.day, "body": "# A\nz\n\n# B\nb", "version": self.opened},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Note.objects.get().body, self.ORIGINAL + "\n- capture")

    def test_remplacer_ne_fusionne_pas(self):
        """« Remplacer par mon texte » remplace, même si une fusion était possible."""
        self.elsewhere(self.ORIGINAL + "\n- capture")
        current = Note.objects.get().updated.isoformat()

        self.save("# A\nz\n\n# B\nb", overwrite=current)

        self.assertEqual(Note.objects.get().body, "# A\nz\n\n# B\nb")
