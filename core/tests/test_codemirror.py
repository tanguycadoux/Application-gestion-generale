"""CodeMirror embarqué : fichiers intacts, import map complète, sans réseau (#89)."""

import base64
import hashlib
import io
import json
import tarfile

from django.template import Context, Template
from django.test import SimpleTestCase

from core import codemirror


def npm_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def npm_integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


class EmbeddedFilesTests(SimpleTestCase):
    def test_chaque_module_est_la_avec_sa_licence(self):
        for package in codemirror.load_packages():
            with self.subTest(package=package.name):
                self.assertTrue((package.path / "index.js").is_file())
                self.assertTrue((package.path / "LICENSE").is_file())

    def test_fichiers_conformes_a_leur_empreinte(self):
        """Un fichier modifié à la main (ou abîmé) est repéré."""
        for package in codemirror.load_packages():
            with self.subTest(package=package.name):
                self.assertTrue(package.integrity.startswith("sha512-"))
                content = (package.path / "index.js").read_bytes()
                self.assertEqual(codemirror.sha256_of(content), package.sha256)

    def test_modules_importes_tous_embarques(self):
        """Aucun module n'est cherché ailleurs que dans notre liste."""
        names = {p.name for p in codemirror.load_packages()}
        for package in codemirror.load_packages():
            source = (package.path / "index.js").read_text(encoding="utf-8")
            with self.subTest(package=package.name):
                self.assertLessEqual(codemirror.imported_specifiers(source), names)

    def test_readme_a_jour(self):
        readme = (codemirror.VENDOR_DIR / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme, codemirror.readme(codemirror.load_packages()))


class ImportMapTests(SimpleTestCase):
    def test_chaque_paquet_pointe_vers_notre_serveur(self):
        imports = codemirror.import_map()["imports"]

        self.assertEqual(
            imports["@codemirror/state"],
            "/static/vendor/codemirror/codemirror-state/index.js",
        )
        self.assertEqual(set(imports), {p.name for p in codemirror.load_packages()})
        for address in imports.values():
            self.assertTrue(address.startswith("/static/"))

    def test_balise_importmap(self):
        html = Template("{% load vendor %}{% codemirror_importmap %}").render(Context())

        self.assertTrue(html.startswith('<script type="importmap">'))
        data = json.loads(
            html.removeprefix('<script type="importmap">').removesuffix("</script>")
        )
        self.assertEqual(data, codemirror.import_map())


class ImportSpecifiersTests(SimpleTestCase):
    def test_import_et_reexport(self):
        source = (
            "import { A } from '@codemirror/state';\n"
            "import elt from 'crelt'\n"
            "export { B } from '@lezer/common';\n"
            "import 'effet-de-bord';\n"
            "const texte = 'from x';\n"
        )

        self.assertEqual(
            codemirror.imported_specifiers(source),
            {"@codemirror/state", "crelt", "@lezer/common", "effet-de-bord"},
        )


class VendorTests(SimpleTestCase):
    def test_empreinte_correcte(self):
        data = npm_archive({"dist/index.js": b"x", "LICENSE": b"MIT"})

        codemirror.check_integrity(data, npm_integrity(data))

    def test_empreinte_differente_refusee(self):
        data = npm_archive({"dist/index.js": b"x", "LICENSE": b"MIT"})

        with self.assertRaises(codemirror.IntegrityError):
            codemirror.check_integrity(data + b"!", npm_integrity(data))

    def test_algorithme_inconnu_refuse(self):
        with self.assertRaises(codemirror.IntegrityError):
            codemirror.check_integrity(b"x", "sha1-abc")

    def test_extraction_entree_et_licence(self):
        data = npm_archive({"dist/index.js": b"export {}", "LICENSE": b"MIT"})

        self.assertEqual(
            codemirror.extract_files(data, "dist/index.js"), (b"export {}", b"MIT")
        )

    def test_entree_absente_refusee(self):
        data = npm_archive({"LICENSE": b"MIT"})

        with self.assertRaises(codemirror.IntegrityError):
            codemirror.extract_files(data, "dist/index.js")
