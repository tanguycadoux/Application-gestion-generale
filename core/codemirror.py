"""CodeMirror 6 embarqué dans static/vendor/codemirror/ (#89).

Les notes sont privées : aucun module n'est chargé depuis un CDN. Chaque paquet npm
de `packages.json` est rangé dans son dossier (`index.js` et `LICENSE`), et une
import map dit au navigateur de les chercher sur notre serveur. Ajouter un module =
ajouter une ligne à `packages.json` (nom, version, fichier d'entrée) puis lancer
`python manage.py vendor_codemirror`.
"""

import base64
import hashlib
import io
import json
import re
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

VENDOR_DIR = Path(settings.BASE_DIR) / "static" / "vendor" / "codemirror"
PACKAGES_FILE = VENDOR_DIR / "packages.json"
REGISTRY_URL = "https://registry.npmjs.org/{name}/{version}"

# `import … from "x"`, `export … from "x"` et `import "x"` d'un module ES.
IMPORT_REGEX = re.compile(
    r"""(?:^|[;}\s])(?:import|export)\b[^;'"()]*?\bfrom\s*['"](?P<from>[^'"]+)['"]"""
    r"""|(?:^|[;}\s])import\s*['"](?P<bare>[^'"]+)['"]""",
    re.MULTILINE,
)


class IntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    entry: str
    integrity: str = ""
    sha256: str = ""

    @property
    def folder(self) -> str:
        return self.name.removeprefix("@").replace("/", "-")

    @property
    def path(self) -> Path:
        return VENDOR_DIR / self.folder

    @property
    def static_path(self) -> str:
        return f"vendor/codemirror/{self.folder}/index.js"


def load_packages() -> list[Package]:
    data = json.loads(PACKAGES_FILE.read_text(encoding="utf-8"))
    return [Package(**item) for item in data]


def save_packages(packages: list[Package]) -> None:
    data = [
        {
            "name": p.name,
            "version": p.version,
            "entry": p.entry,
            "integrity": p.integrity,
            "sha256": p.sha256,
        }
        for p in packages
    ]
    PACKAGES_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def import_map() -> dict[str, dict[str, str]]:
    """Import map : nom du paquet -> adresse du fichier sur notre serveur."""
    return {
        "imports": {p.name: static(p.static_path) for p in load_packages()},
    }


def imported_specifiers(source: str) -> set[str]:
    """Modules qu'un fichier JavaScript importe (ou ré-exporte)."""
    return {m.group("from") or m.group("bare") for m in IMPORT_REGEX.finditer(source)}


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_integrity(data: bytes, integrity: str) -> None:
    """Vérifie une empreinte npm (`sha512-<base64>`)."""
    algorithm, _, expected = integrity.partition("-")
    if algorithm != "sha512":
        raise IntegrityError(f"Empreinte non prise en charge : {integrity!r}.")
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if actual != expected:
        raise IntegrityError("L'empreinte de l'archive ne correspond pas.")


def extract_files(archive: bytes, entry: str) -> tuple[bytes, bytes]:
    """(fichier d'entrée, licence) d'une archive npm."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:

        def read(name: str) -> bytes:
            try:
                member = tar.extractfile(f"package/{name}")
            except KeyError:
                member = None
            if member is None:
                raise IntegrityError(f"{name} est absent de l'archive.")
            return member.read()

        names = {m.name.lower(): m.name for m in tar.getmembers()}
        license_name = names.get("package/license", "package/LICENSE")
        return read(entry), read(license_name.removeprefix("package/"))


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def vendor(package: Package) -> Package:
    """Télécharge un paquet, vérifie son empreinte et le range dans son dossier.

    Une empreinte déjà notée dans `packages.json` doit être celle du registre.
    """
    try:
        meta = json.loads(
            fetch(REGISTRY_URL.format(name=package.name, version=package.version))
        )
        integrity = meta["dist"]["integrity"]
        if package.integrity and package.integrity != integrity:
            raise IntegrityError(
                f"{package.name} {package.version} : l'empreinte du registre a changé."
            )
        archive = fetch(meta["dist"]["tarball"])
    except urllib.error.URLError as error:
        raise IntegrityError(
            f"{package.name} {package.version} : téléchargement impossible ({error})."
        ) from error
    check_integrity(archive, integrity)
    entry, license_text = extract_files(archive, package.entry)
    package.path.mkdir(parents=True, exist_ok=True)
    (package.path / "index.js").write_bytes(entry)
    (package.path / "LICENSE").write_bytes(license_text)
    return Package(
        package.name, package.version, package.entry, integrity, sha256_of(entry)
    )


def readme(packages: list[Package]) -> str:
    rows = "\n".join(
        f"| `{p.name}` | {p.version} | `{p.entry}` | `{p.sha256}` | `{p.integrity}` |"
        for p in packages
    )
    return f"""# CodeMirror 6

Éditeur des notes (#89), chargé par `note_taking/static/note_taking/editor.js` \
sur les pages de création et de modification d'une note. Rien n'est chargé depuis \
Internet : une import map (`{{% codemirror_importmap %}}`) renvoie chaque module \
vers ce dossier.

Fichier généré par `python manage.py vendor_codemirror` à partir de \
`packages.json` ; ne pas le modifier à la main.

- Source : archives npm officielles (`https://registry.npmjs.org/<paquet>/-/…tgz`), \
dont l'empreinte (`dist.integrity` du registre) est vérifiée avant l'extraction.
- Fichiers : `index.js` (le fichier d'entrée ES indiqué) et `LICENSE` de chaque \
paquet, dans un dossier au nom du paquet (`@codemirror/state` → `codemirror-state/`).
- Versions : la plus récente publiée depuis au moins deux semaines au moment du choix.
- Ajouter un module : une ligne dans `packages.json` (nom, version, fichier d'entrée), \
puis `python manage.py vendor_codemirror`. Un test vérifie que tous les modules \
importés par ces fichiers sont dans la liste.

| Paquet | Version | Fichier d'entrée | SHA-256 de `index.js` | Empreinte de l'archive |
|---|---|---|---|---|
{rows}
"""
