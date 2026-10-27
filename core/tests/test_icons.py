"""Tests des icônes : tout bouton a une icône, une par action (#131)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

APPS = ("core", "images", "note_taking", "todolist")

BUTTON_TAG_REGEX = re.compile(r"\{% button .*?%\}")
ICON_REGEX = re.compile(r'\bicon="(?P<icon>[a-z_]+)"')

# Une icône par action, la même partout (README, section Composants).
ACTION_ICONS = {
    "Créer": "add",
    "Ajouter": "add",
    "Modifier": "edit",
    "Supprimer": "delete",
    "Renommer": "edit",
    "Écarter": "playlist_remove",
    "Rétablir": "restore_from_trash",
    "Enregistrer": "save",
    "Exporter": "download",
    "Importer": "upload",
}


def button_tags() -> list[tuple[Path, str]]:
    return [
        (path, tag)
        for app in APPS
        for path in (Path(settings.BASE_DIR) / app).glob("**/templates/**/*.html")
        for tag in BUTTON_TAG_REGEX.findall(path.read_text(encoding="utf-8"))
    ]


class IconTests(SimpleTestCase):
    def test_boutons_trouves(self):
        self.assertGreater(len(button_tags()), 15)

    def test_tout_bouton_a_une_icone(self):
        for path, tag in button_tags():
            with self.subTest(path=path.name, tag=tag):
                self.assertRegex(tag, ICON_REGEX)

    def test_pas_d_icone_ecrite_dans_le_libelle(self):
        for path, tag in button_tags():
            with self.subTest(path=path.name, tag=tag):
                self.assertNotRegex(tag, r'\{% button "[+✓×]')

    def test_une_icone_par_action(self):
        for path, tag in button_tags():
            label = re.match(r'\{% button "(?P<label>[^"]*)"', tag)
            icon = ICON_REGEX.search(tag)
            if label is None or icon is None:
                continue
            verb = label.group("label").split()[0]
            if verb in ACTION_ICONS:
                with self.subTest(path=path.name, tag=tag):
                    self.assertEqual(icon.group("icon"), ACTION_ICONS[verb])
