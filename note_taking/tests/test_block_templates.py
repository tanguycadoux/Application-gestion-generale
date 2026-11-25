"""Blocs du menu « Insérer » de l'éditeur (#420) : chaque squelette est un bloc que le
rendu comprend (le JavaScript n'est pas exécuté par les tests, sa source est lue)."""

import json
import re
import unittest
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from note_taking.rendering import CALLOUT_ICONS, render_note_body

SCRIPT = (
    Path(settings.BASE_DIR)
    / "note_taking"
    / "static"
    / "note_taking"
    / "block_templates.js"
)
STRING = r'"(?:[^"\\\n]|\\.)*"'


def skeletons() -> dict[str, list[str]]:
    """Les squelettes écrits en toutes lettres : libellé -> `skeleton`, puis `wrap`."""
    found: dict[str, list[str]] = {}
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        label = re.search(rf"label: ({STRING})", line)
        texts = re.findall(rf"(?:skeleton|wrap): ({STRING})", line)
        if label and texts:
            found[json.loads(label[1])] = [json.loads(text) for text in texts]
    return found


def typed(skeleton: str) -> str:
    """Le squelette une fois du texte écrit à la place du curseur ou enveloppé."""
    return (
        re.sub(r"«(.*?)»", lambda match: match[1] or "x", skeleton)
        .replace("¦", "x")
        .replace("TYPE", "note")
    )


class BlockTemplatesTests(TestCase):
    def rendered(self, label: str, context: str = "{}") -> list[str]:
        """Le rendu de chaque squelette de cette entrée, `{}` dans `context`."""
        return [
            render_note_body(
                "avant\n\n" + context.replace("{}", typed(skeleton)) + "\n\naprès\n"
            )
            for skeleton in skeletons()[label]
        ]

    @unittest.expectedFailure
    def test_callout_avec_son_titre_et_son_texte(self):
        for html in self.rendered("Callout"):
            self.assertIn('class="callout callout-note"', html)
            self.assertIn('<span class="callout-title">Titre (optionnel)</span>', html)
            self.assertNotIn(":::", html)

    @unittest.expectedFailure
    def test_formules(self):
        for html in self.rendered("En bloc"):
            self.assertIn('<span class="math display">', html)
        for html in self.rendered("Dans la ligne"):
            self.assertIn('<span class="math inline">\\(x\\)</span>', html)

    @unittest.expectedFailure
    def test_metadonnees_lues_par_l_analyse(self):
        for html in self.rendered("Métadonnées"):
            self.assertIn('<ul class="note-tags', html)
            self.assertNotIn(":::", html)

    @unittest.expectedFailure
    def test_legende_et_renvois_ont_les_memes_identifiants(self):
        for html in self.rendered(
            "Légende de tableau", "|a|\n|-|\n|b|\n\n{}\n\nvoir @tbl-nom"
        ):
            self.assertIn("<caption>Table 1: Légende</caption>", html)
            self.assertIn('<a href="#tbl-nom" class="quarto-xref">', html)
        for label, prefix in (("Vers une figure", "fig"), ("Vers un tableau", "tbl")):
            self.assertEqual(skeletons()[label], [f"@{prefix}-«nom»"])

    @unittest.expectedFailure
    def test_mise_en_page_lue_par_le_rendu(self):
        """Squelettes calculés (nombre choisi) : la syntaxe que le rendu reconnaît."""
        source = SCRIPT.read_text(encoding="utf-8")

        for opening in (
            "::: {.columns}",
            '::: {.column width="${',
            "::: {#fig-nom layout-ncol=${",
        ):
            self.assertIn(opening, source)


class BlockMenuTests(TestCase):
    @unittest.expectedFailure
    def test_chaque_type_de_callout_est_dans_le_menu(self):
        """Types, libellés et icônes viennent du serveur : le script les clone."""
        html = self.client.get(reverse("note_taking:new_note")).content.decode()

        self.assertEqual(
            re.findall(
                r'<template data-callout="(\w+)" data-label="\w+">'
                r'<span class="callout-\1"><svg',
                html,
            ),
            list(CALLOUT_ICONS),
        )

    @unittest.expectedFailure
    def test_insertion_en_une_modification(self):
        """Un seul `dispatch` : un Ctrl+Z annule l'insertion."""
        self.assertEqual(SCRIPT.read_text(encoding="utf-8").count("view.dispatch("), 1)
