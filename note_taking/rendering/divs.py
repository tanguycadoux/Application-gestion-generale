"""Blocs Quarto `::: {…} … :::` : leur fin et leur découpage, hors code."""

import re

# Blocs Quarto ::: {…} … :::, éventuellement imbriqués
DIV_START_REGEX = re.compile(r"^:::+\s*\{[^}]*\}$")
DIV_END_REGEX = re.compile(r"^:::+$")
DIV_ID_REGEX = re.compile(r"#(?P<id>[\w-]+)")


CODE_FENCE = "```"


def find_block_end(lines: list[str], start: int) -> int | None:
    """Indice de la ligne fermant le bloc ouvert à `start`, s'il existe.

    Tient compte des blocs imbriqués ; les blocs de code sont ignorés.
    """
    depth = 1
    in_code_block = False
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif in_code_block:
            continue
        elif DIV_START_REGEX.match(stripped):
            depth += 1
        elif DIV_END_REGEX.match(stripped):
            depth -= 1
            if depth == 0:
                return index
    return None


def split_blocks(lines: list[str]) -> list[str]:
    """Découpe en blocs séparés par des lignes vides, hors code et blocs `:::`."""
    blocks: list[list[str]] = [[]]
    depth = 0
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(CODE_FENCE):
            in_code_block = not in_code_block
        elif not in_code_block and DIV_START_REGEX.match(stripped):
            depth += 1
        elif not in_code_block and depth and DIV_END_REGEX.match(stripped):
            depth -= 1

        if not stripped and not in_code_block and depth == 0:
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks if block]
