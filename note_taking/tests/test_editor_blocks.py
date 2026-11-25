"""Titres dans un bloc `:::` de l'éditeur (#423) : ce que le JavaScript promet (il n'est
pas exécuté par les tests)."""

import re
from pathlib import Path
from unittest import expectedFailure

from django.conf import settings
from django.test import SimpleTestCase

from note_taking.rendering import blocks, divs

STATIC_DIR = Path(settings.BASE_DIR) / "note_taking" / "static" / "note_taking"


class EditorBlocksTests(SimpleTestCase):
    def read(self, name: str) -> str:
        return (STATIC_DIR / name).read_text(encoding="utf-8")

    @expectedFailure
    def test_titres_des_blocs_ecartes_du_plan_et_des_suggestions(self):
        outline = self.read("outline.js")

        self.assertIn("closedBlocks(state.doc)", outline)
        # Les suggestions de chemins partent des mêmes titres.
        self.assertIn("readHeadings(context.state)", self.read("suggestions.js"))

    @expectedFailure
    def test_memes_blocs_que_le_rendu(self):
        """Les motifs de `blocks.js` sont ceux du rendu : un bloc ajouté d'un côté sans
        l'autre ferait diverger le plan."""
        script = self.read("blocks.js")
        for pattern in (
            divs.DIV_START_REGEX,
            divs.DIV_END_REGEX,
            blocks.CALLOUT_START_REGEX,
            blocks.LAYOUT_START_REGEX,
            blocks.COLUMNS_START_REGEX,
            blocks.METADATA_START_REGEX,
        ):
            # Sans les noms de groupes ni les échappements propres à Python.
            wanted = re.sub(r"\?P<\w+>", "", pattern.pattern).replace("\\ ", " ")
            with self.subTest(pattern=wanted):
                self.assertIn(f"/{wanted}/", script)
