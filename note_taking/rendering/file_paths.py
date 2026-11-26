"""Liens vers un fichier local ou réseau (#496), écart voulu à Pandoc : un navigateur
n'ouvre pas un fichier depuis une page web. Le texte du lien est suivi d'un bouton
« Copier le chemin », pour coller le chemin dans l'Explorateur.

Le lien est lu par le Markdown (`FilePathLinkExtension`), avant que les barres obliques
inversées n'y soient des échappements ; il en sort un repère que le filtrage garde, et
que `file_path_buttons` remplace, après le filtrage, par le bouton.
"""

import html as html_module
import re
import xml.etree.ElementTree as etree
from urllib.parse import unquote

import markdown
from django.utils.html import format_html
from markdown.inlinepatterns import NOIMG, LinkInlineProcessor
from markdown.util import AtomicString

from core.icons import icon_svg

# Cible d'un lien qui est un fichier : lecteur Windows (`C:\…`, `C:/…`), chemin réseau
# (`\\serveur\partage`, `//serveur/partage`), adresse `file:`. Un chemin Linux ou macOS
# (`/home/…`) ne se distingue pas d'une adresse du site : il reste un lien.
FILE_TARGET_REGEX = re.compile(
    r"[a-z]:[\\/]|(?:\\\\|//)[^\\/\s]+[\\/]|file:", re.IGNORECASE
)
DRIVE_REGEX = re.compile(r"[a-z]:(?:[\\/]|$)", re.IGNORECASE)
LEADING_SLASHES_REGEX = re.compile(r"/*")
SEPARATORS_REGEX = re.compile(r"[\\/]+")

# Avant le lien de Python-Markdown (160) et ses échappements (180), après le code (190).
PRIORITY = 185
MARKER_CLASS = "file-path-copy-marker"
# Repère du HTML filtré : la cible écrite, dans son `title`.
MARKER_REGEX = re.compile(
    rf'<span class="{MARKER_CLASS}" title="(?P<target>[^"]*)"></span>'
)

BUTTON_CLASSES = (
    "file-path-copy ml-1 inline-flex rounded-sm align-[-0.125em] text-slate-500 "
    "hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-blue-700"
)


def copied_path(target: str) -> str:
    """Le chemin à coller dans l'Explorateur : `C:\\…`, `\\\\serveur\\…`.

    D'une adresse `file:`, le schéma est retiré et les `%20` décodés ; un chemin Linux y
    reste tel quel.
    """
    if target[:5].lower() != "file:":
        if target[:2] in ("//", "\\\\"):
            return "\\\\" + target.lstrip("/\\").replace("/", "\\")
        return target.replace("/", "\\")
    path = unquote(target[5:])
    slashes = LEADING_SLASHES_REGEX.match(path)
    count = slashes.end() if slashes else 0
    body = path[count:]
    if DRIVE_REGEX.match(body):
        return body.replace("/", "\\")
    # `file://serveur/…` ou `file:////serveur/…` ; `file:///…` est un chemin local.
    if count == 2 or count >= 4:
        return "\\\\" + body.replace("/", "\\")
    return "/" + body


def file_name(path: str) -> str:
    """Le dernier élément du chemin, ou le chemin entier (`C:\\`)."""
    parts = [part for part in SEPARATORS_REGEX.split(path) if part]
    return parts[-1] if len(parts) > 1 or not DRIVE_REGEX.match(path) else path


class FilePathLinkProcessor(LinkInlineProcessor):
    """`[texte](C:\\…)` : le texte, suivi du repère du bouton. Un autre lien est laissé
    au lien de Python-Markdown."""

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[etree.Element | None, int | None, int | None]:
        text, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None
        target, _, index, handled = self.getLink(data, index)
        if not handled or not FILE_TARGET_REGEX.match(target):
            return None, None, None
        span = etree.Element("span", {"class": "file-path"})
        # Sans texte, le nom du fichier, lu tel quel (`plan_v2_final.pdf`).
        span.text = (
            text if text.strip() else AtomicString(file_name(copied_path(target)))
        )
        etree.SubElement(span, "span", {"class": MARKER_CLASS, "title": target})
        return span, m.start(0), index


class FilePathLinkExtension(markdown.Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Un crochet échappé (`\[`) n'ouvre pas de lien.
        pattern = NOIMG + r"(?<!\\)\["
        md.inlinePatterns.register(
            FilePathLinkProcessor(pattern, md), "file_path_link", PRIORITY
        )


def file_path_buttons(html: str) -> str:
    """Remplace chaque repère du HTML filtré par le bouton « Copier le chemin ».

    Le bouton n'a pas de texte (une icône et son `aria-label`) : il n'entre pas dans le
    texte d'un titre. À l'impression, le chemin s'affiche à sa place (`style.css`).
    """

    def button(match: re.Match[str]) -> str:
        path = copied_path(html_module.unescape(match["target"]))
        return format_html(
            '<button type="button" class="{}" data-copy-path="{}" title="{}"'
            ' aria-label="Copier le chemin de {}">{}</button>',
            BUTTON_CLASSES,
            path,
            path,
            file_name(path),
            icon_svg("content_copy", "size-[1em]"),
        )

    return MARKER_REGEX.sub(button, html)
