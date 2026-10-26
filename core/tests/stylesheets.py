"""Source de la feuille Tailwind (#217), lue par les tests de style."""

from pathlib import Path

from django.conf import settings

SOURCE_CSS = Path(settings.BASE_DIR) / settings.TAILWIND_CLI_SRC_CSS


def read_source_css() -> str:
    return SOURCE_CSS.read_text(encoding="utf-8")


def components_layer(css: str) -> str:
    """Contenu du bloc `@layer components { … }`."""
    start = css.index("@layer components {")
    depth = 0
    for i in range(start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start : i + 1]
    raise ValueError("bloc @layer components non fermé")
