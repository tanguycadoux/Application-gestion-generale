// Blocs `:::` de Quarto dans le texte de l'éditeur (#423), avec les motifs du rendu
// (`rendering/divs.py` et `rendering/blocks.py`) : un test vérifie que ce sont les mêmes.
const DIV_START = /^:::+\s*\{[^}]*\}$/;
const DIV_END = /^:::+$/;
// Blocs rendus à part : callout, figure en colonnes, colonnes, métadonnées. Un autre bloc
// reste du texte dans la page, et ses titres sont ceux de la note.
const RENDERED = [
    /^:::\s*\{\.callout-(\w+)([^}]*)\}$/,
    /^:::\s*\{([^}]*\blayout-ncol=(\d+)[^}]*)\}$/,
    /^:::\s*\{\.columns\}$/,
    /^::: \{\.metadata\}$/,
];
const CODE_FENCE = "```";

/** Indice de la ligne qui ferme le bloc ouvert à `start`, ou -1 : blocs imbriqués et code compris. */
function blockEnd(lines, start) {
    let depth = 1;
    let code = false;
    for (let i = start + 1; i < lines.length; i++) {
        if (lines[i].startsWith(CODE_FENCE)) code = !code;
        else if (code) continue;
        else if (DIV_START.test(lines[i])) depth++;
        else if (DIV_END.test(lines[i]) && --depth === 0) return i;
    }
    return -1;
}

/**
 * Les blocs rendus à part et fermés, les plus hauts seulement : `{ first, last }`, numéros de
 * lignes à partir de 1. Un bloc pas encore fermé reste du texte, comme dans la page.
 */
export function closedBlocks(doc) {
    const lines = doc.toString().split("\n").map((line) => line.trim());
    const blocks = [];
    let code = false;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].startsWith(CODE_FENCE)) code = !code;
        if (code || !RENDERED.some((start) => start.test(lines[i]))) continue;
        const end = blockEnd(lines, i);
        if (end < 0) continue;
        blocks.push({ first: i + 1, last: end + 1 });
        i = end;
    }
    return blocks;
}
