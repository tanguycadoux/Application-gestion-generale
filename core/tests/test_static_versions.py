"""L'adresse d'un fichier statique change avec son contenu (#469)."""

import json
import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

VERSION = r"\?v=[0-9a-f]{12}"
IMPORT_MAP_REGEX = re.compile(
    r'<script type="importmap">(?P<json>.*?)</script>', re.DOTALL
)
# Adresse d'un fichier statique citée par une page.
ADDRESS_REGEX = re.compile(r'(?:src|href)="(?P<address>/static/[^"]+)"')


class StaticVersionTests(SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.file = Path(directory.name) / "essai.js"
        self.write("un")
        overridden = override_settings(STATICFILES_DIRS=[directory.name])
        overridden.enable()
        self.addCleanup(overridden.disable)

    def write(self, content: str, mtime: int = 1) -> None:
        self.file.write_text(content, encoding="utf-8")
        os.utime(self.file, (mtime, mtime))

    def test_adresse_avec_empreinte(self):
        self.assertRegex(static("essai.js"), rf"^/static/essai\.js{VERSION}$")

    def test_contenu_change_adresse_change(self):
        before = static("essai.js")

        self.write("deux", mtime=2)

        self.assertNotEqual(static("essai.js"), before)

    def test_meme_contenu_meme_adresse(self):
        """Une date de fichier qui change (clone, changement de branche) ne suffit pas."""
        before = static("essai.js")
        self.assertIn("?v=", before)

        self.write("un", mtime=2)

        self.assertEqual(static("essai.js"), before)

    def test_fichier_absent_sans_empreinte(self):
        """La feuille Tailwind pas encore construite ne fait pas échouer la page."""
        self.assertEqual(static("absent.css"), "/static/absent.css")

    def test_dossier_sans_empreinte(self):
        (self.file.parent / "dossier").mkdir()

        self.assertEqual(static("dossier/"), "/static/dossier/")


class PageAddressesTests(TestCase):
    def test_toutes_les_adresses_des_pages_ont_une_empreinte(self):
        for name in (
            "core:index",
            "core:projects",
            "note_taking:index",
            "note_taking:new_note",
            "note_taking:images_list",
            "todolist:index",
        ):
            html = self.client.get(reverse(name)).content.decode()
            addresses = ADDRESS_REGEX.findall(html)
            self.assertTrue(addresses)
            for address in addresses:
                path, _, version = address.partition("?v=")
                if finders.find(path.removeprefix("/static/")) is None:
                    continue  # Tailwind n'est pas construite en CI.
                with self.subTest(page=name, address=address):
                    self.assertRegex(version, r"^[0-9a-f]{12}$")


class ModuleVersionsTests(TestCase):
    """Un module importé par `./x.js` n'a pas d'adresse dans le gabarit : l'import map
    renvoie son adresse nue vers celle qui porte l'empreinte."""

    def imports(self, name: str) -> dict[str, str]:
        html = self.client.get(reverse(name)).content.decode()
        found = IMPORT_MAP_REGEX.search(html)
        assert found is not None
        self.assertLess(found.start(), html.index('<script type="module"'))
        return json.loads(found["json"])["imports"]

    def relative_modules(self, *names: str) -> set[str]:
        """Modules importés de proche en proche, en repartant des fichiers."""
        root = Path(settings.BASE_DIR) / "note_taking/static/note_taking"
        found: set[str] = set()
        todo = list(names)
        while todo:
            source = (root / todo.pop()).read_text(encoding="utf-8")
            for module in re.findall(r'from "\./([\w-]+\.js)"', source):
                if module not in found:
                    found.add(module)
                    todo.append(module)
        return found

    def check(self, page: str, entry: str) -> None:
        imports = self.imports(page)
        modules = self.relative_modules(entry)
        self.assertTrue(modules)
        for module in modules:
            address = f"/static/note_taking/{module}"
            with self.subTest(module=module):
                self.assertRegex(imports[address], rf"^{re.escape(address)}{VERSION}$")

    def test_modules_de_l_editeur(self):
        self.check("note_taking:new_note", "editor.js")

    def test_modules_de_la_page_des_images(self):
        self.check("note_taking:images_list", "images_capture.js")


class EditorGuardTests(SimpleTestCase):
    """Le script n'est pas exécuté par les tests : ce qu'il promet, lu dans sa source."""

    def test_version_absente_de_la_reponse_signalee(self):
        path = finders.find("note_taking/note_form.js")
        source = Path(str(path)).read_text(encoding="utf-8")

        self.assertIn("if (form.elements.version && !version)", source)
        self.assertIn("Rechargez la page", source)
