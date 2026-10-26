"""Validateur HTML du W3C (Nu Html Checker), utilisé en local, jamais en ligne (#259).

Le validateur en ligne recevrait le HTML des pages, donc le contenu des notes.
`vnu.jar` est téléchargé une fois depuis le registre npm (paquet `vnu-jar`), en
version épinglée et intégrité vérifiée, dans `.vnu/` (non versionné). Il demande
Java. La CI l'installe et valide les pages à chaque PR.
"""

import base64
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from django.conf import settings

VNU_DIR = Path(settings.BASE_DIR) / ".vnu"
VNU_JAR = VNU_DIR / "vnu.jar"
TARBALL_URL = "https://registry.npmjs.org/vnu-jar/-/vnu-jar-{version}.tgz"
JAR_IN_TARBALL = "package/build/dist/vnu.jar"


def is_available() -> bool:
    return VNU_JAR.exists() and shutil.which("java") is not None


def install() -> Path:
    """Télécharge `vnu.jar` dans `.vnu/`, après vérification de son intégrité."""
    url = TARBALL_URL.format(version=settings.VNU_VERSION)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    algorithm, expected = settings.VNU_INTEGRITY.split("-", 1)
    digest = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if digest != expected:
        raise ValueError(f"Intégrité de {url} incorrecte : {algorithm}-{digest}.")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = archive.extractfile(JAR_IN_TARBALL)
        assert member is not None
        VNU_DIR.mkdir(exist_ok=True)
        VNU_JAR.write_bytes(member.read())
    return VNU_JAR


def validate(paths: list[Path]) -> list[str]:
    """Erreurs du validateur pour ces fichiers HTML : « fichier:ligne : message »."""
    result = subprocess.run(
        [
            "java",
            "-jar",
            str(VNU_JAR),
            "--errors-only",
            "--format",
            "json",
            "--exit-zero-always",
            *map(str, paths),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    messages = json.loads(result.stderr or '{"messages": []}')["messages"]
    return [
        f"{Path(m.get('url', '')).name}:{m.get('lastLine', '?')} : {m['message']}"
        for m in messages
        if m.get("type") == "error"
    ]
