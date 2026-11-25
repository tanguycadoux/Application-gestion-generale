"""Adresses des fichiers statiques : elles changent avec leur contenu (#469).

Servi sous une adresse fixe, un script peut rester en cache après une mise à jour : la
page est neuve, son script est ancien. L'empreinte du contenu, ajoutée à l'adresse, le
fait redemander. `{% static %}` et `static()` passent par ce stockage : aucun gabarit
n'a à y penser.
"""

import hashlib
import posixpath
from functools import lru_cache
from pathlib import Path

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage, staticfiles_storage
from django.templatetags.static import static

from core.codemirror import imported_specifiers


def find_file(name: str) -> Path | None:
    found = finders.find(name)
    if not isinstance(found, str) or not Path(found).is_file():
        return None
    return Path(found)


@lru_cache(maxsize=1024)
def _fingerprint(path: Path, mtime_ns: int, size: int) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def fingerprint(path: Path) -> str:
    """Empreinte du contenu, relue seulement si le fichier a changé."""
    stat = path.stat()
    return _fingerprint(path, stat.st_mtime_ns, stat.st_size)


class VersionedStaticFilesStorage(StaticFilesStorage):
    def plain_url(self, name: str) -> str:
        """Adresse sans empreinte, celle d'un import relatif vue par le navigateur."""
        return super().url(name)

    def url(self, name: str | None) -> str:
        url = super().url(name)
        path = find_file(name) if name else None
        return url if path is None else f"{url}?v={fingerprint(path)}"


@lru_cache(maxsize=1024)
def _relative_imports(path: Path, mtime_ns: int, size: int) -> tuple[str, ...]:
    specifiers = imported_specifiers(path.read_text(encoding="utf-8"))
    return tuple(sorted(s for s in specifiers if s.startswith(".")))


def relative_modules(*entries: str) -> list[str]:
    """Modules importés par `./x.js`, de proche en proche, depuis les scripts donnés."""
    found: set[str] = set()
    todo = list(entries)
    while todo:
        name = todo.pop()
        path = find_file(name)
        if path is None:
            continue
        stat = path.stat()
        for specifier in _relative_imports(path, stat.st_mtime_ns, stat.st_size):
            module = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), specifier)
            )
            if module not in found:
                found.add(module)
                todo.append(module)
    return sorted(found)


def module_imports(*entries: str) -> dict[str, str]:
    """Import map de ces modules : adresse nue -> adresse avec l'empreinte.

    Le navigateur résout `./x.js` en une adresse sans empreinte, qu'il cherche ensuite
    dans l'import map.
    """
    assert isinstance(staticfiles_storage, VersionedStaticFilesStorage)
    return {
        staticfiles_storage.plain_url(name): static(name)
        for name in relative_modules(*entries)
    }
