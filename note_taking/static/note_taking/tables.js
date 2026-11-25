// Tableaux de l'éditeur (#401, #402). Les tableaux sont ceux à barres (`| a | b |`, les
// « pipe tables » de Pandoc), reconnus par l'extension `Table` de @lezer/markdown : un
// tableau dans un bloc de code n'en est pas un. Les tableaux en grille (`+---+`) ne sont pas
// reconnus : « Formater » ne les touche pas.
//
// - `formatTable` aligne les colonnes : chaque cellule prend la largeur de la plus large de
//   sa colonne, comptée en caractères affichés (un « é » décomposé compte pour un, un
//   caractère chinois ou un emoji pour deux). Un tableau à barres n'a qu'une ligne par
//   cellule : il n'y a pas de hauteur à égaliser.
// - `tableLines` : les lignes d'un tableau ne reviennent pas à la ligne (#402). Elles
//   débordent, et tout l'éditeur défile horizontalement d'un seul tenant : les colonnes
//   restent alignées. Les paragraphes gardent leur retour à la ligne.
import { ensureSyntaxTree, syntaxTree } from "@codemirror/language";
import { EditorSelection, RangeSetBuilder } from "@codemirror/state";
import { Decoration, ViewPlugin } from "@codemirror/view";

const DELIMITER_CELL = /^:?-+:?$/;
// `: Légende`, ou le `:::` d'un bloc (`TABLE_CAPTION_REGEX`, `rendering/tables.py`).
const CAPTION = /^\s*(?:[Tt]able)?:/;
const WIDE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}　-〿！-｠￠-￦]|\p{Extended_Pictographic}/u;
const segmenter = typeof Intl.Segmenter === "function" ? new Intl.Segmenter() : null;

/** Largeur affichée d'un texte : un caractère perçu compte pour 1, un caractère large pour 2. */
export function displayWidth(text) {
    const graphemes = segmenter ? [...segmenter.segment(text)].map((s) => s.segment) : [...text];
    return graphemes.reduce((total, grapheme) => total + (WIDE.test(grapheme) ? 2 : 1), 0);
}

/**
 * Les positions des barres qui séparent les cellules de `line`, lues comme le rendu
 * (`TableProcessor` de Python-Markdown) : ni `\|`, ni une barre dans du code.
 */
function barPositions(line) {
    const bars = [];
    const ticks = [];
    for (const { 0: text, 1: escaped, 2: plain, 3: bar, index } of line.matchAll(/\\\\|(\\`+)|(`+)|\\\||(\|)/g)) {
        if (bar) bars.push(index);
        // Un accent grave échappé n'ouvre pas de code, mais peut en fermer.
        else if (escaped) ticks.push({ from: index, to: index + text.length, size: text.length - 1, opens: text.length - 2 });
        else if (plain) ticks.push({ from: index, to: index + text.length, size: text.length, opens: text.length });
    }
    const code = [];
    for (let open = 0; open < ticks.length; open++) {
        const { from, opens } = ticks[open];
        const close = opens ? ticks.findIndex(({ size }, index) => index > open && size === opens) : -1;
        if (close < 0) continue;
        code.push({ from, to: ticks[close].to });
        open = close;
    }
    return bars.filter((bar) => !code.some(({ from, to }) => from <= bar && bar < to));
}

/**
 * Où sont les cellules d'une ligne, `{ from, to }` entre deux barres, espaces compris. Sans
 * barre au bord de l'en-tête (`edges` faux), une barre qui commence une ligne suit une
 * première cellule vide, comme dans le rendu.
 */
export function cellRanges(line, edges = true) {
    const bars = barPositions(line);
    let from = line.length - line.trimStart().length;
    let end = line.trimEnd().length;
    // Les barres du bord n'ouvrent pas de cellule.
    if (edges && bars[0] === from) from = bars.shift() + 1;
    if (bars.length && bars.at(-1) === end - 1) end = bars.pop();
    const ranges = [];
    for (const bar of bars) {
        ranges.push({ from, to: bar });
        from = bar + 1;
    }
    ranges.push({ from, to: Math.max(from, end) });
    return ranges;
}

/** Vrai si l'en-tête d'un tableau a une barre à un bord. */
export function hasEdges(header) {
    const text = header.trim();
    const bars = barPositions(text);
    return bars[0] === 0 || bars.at(-1) === text.length - 1;
}

/** Le texte des cellules d'un tableau, ligne par ligne. */
export function splitTable(lines) {
    const edges = hasEdges(lines[0]);
    return lines.map((line, index) =>
        cellRanges(line, edges || index === 1).map(({ from, to }) => line.slice(from, to).trim()),
    );
}

function alignmentOf(cell) {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return "";
}

function pad(text, width, alignment) {
    const space = width - displayWidth(text);
    if (alignment === "right") return " ".repeat(space) + text;
    if (alignment === "center") {
        const before = Math.floor(space / 2);
        return " ".repeat(before) + text + " ".repeat(space - before);
    }
    return text + " ".repeat(space);
}

function delimiter(width, alignment) {
    const dashes = "-".repeat(width);
    if (alignment === "center") return `:${dashes.slice(2)}:`;
    if (alignment === "left") return `:${dashes.slice(1)}`;
    if (alignment === "right") return `${dashes.slice(1)}:`;
    return dashes;
}

/**
 * Le tableau à barres `text` (ses lignes, sans légende) aligné ; `null` si ce n'en est pas un
 * (pas de ligne de séparation `|---|` en deuxième ligne). Les alignements `:---:` sont
 * gardés, une ligne trop courte reçoit des cellules vides, le retrait de la première ligne
 * est repris. Le rendu du tableau ne change pas.
 */
export function formatTable(text) {
    const lines = text.split("\n");
    if (lines.length < 2) return null;
    const indent = /^\s*/.exec(lines[0])[0];
    const rows = splitTable(lines);
    if (!rows[1].every((cell) => DELIMITER_CELL.test(cell))) return null;
    const alignments = rows[1].map(alignmentOf);
    const columns = Math.max(...rows.map((row) => row.length));
    const widths = Array.from({ length: columns }, (_, column) =>
        Math.max(3, ...rows.map((row, index) => (index === 1 ? 0 : displayWidth(row[column] ?? "")))),
    );
    return rows
        .map((row, index) => {
            const cells = widths.map((width, column) =>
                index === 1
                    ? delimiter(width, alignments[column] ?? "")
                    : pad(row[column] ?? "", width, alignments[column] ?? ""),
            );
            return `${indent}| ${cells.join(" | ")} |`;
        })
        .join("\n");
}

/** Le tableau à barres qui contient `pos` : `{ from, to }` de ses lignes, sinon `null`. */
export function tableAt(state, pos) {
    for (let node = syntaxTree(state).resolveInner(pos, -1); node; node = node.parent) {
        if (node.name === "Table") {
            return { from: state.doc.lineAt(node.from).from, to: state.doc.lineAt(node.to).to };
        }
    }
    for (let node = syntaxTree(state).resolveInner(pos, 1); node; node = node.parent) {
        if (node.name === "Table") {
            return { from: state.doc.lineAt(node.from).from, to: state.doc.lineAt(node.to).to };
        }
    }
    return null;
}

/**
 * Le numéro de la dernière ligne du tableau qui va de `first` à `last` : l'analyseur en fait
 * aussi une ligne de la légende, ou du `:::`, collés dessous.
 */
function lastRow(state, first, last) {
    for (let number = first + 2; number <= last; number++) {
        const { text } = state.doc.line(number);
        if (!CAPTION.test(text)) continue;
        // Sans barres au bord, une cellule peut commencer par « : ».
        const barred = state.doc.line(number - 1).text.trimStart().startsWith("|");
        if (barred || cellRanges(text).length === 1) return number - 1;
    }
    return last;
}

/**
 * Les tableaux à barres de la note, dans l'ordre : `{ from, to, formatted }`, sans ceux que
 * `formatTable` ne reconnaît pas, ni ceux qui suivent une puce ou un `>` sur leur ligne. Avec `ranges`, seulement ceux que ces sélections touchent,
 * même en partie. L'arbre est celui de toute la note, pas de la partie visible (#437).
 */
export function findTables(state, ranges = null) {
    const tree = ensureSyntaxTree(state, state.doc.length, 2000) ?? syntaxTree(state);
    const found = [];
    tree.iterate({
        enter(node) {
            if (node.name !== "Table") return;
            const { from, number, text } = state.doc.lineAt(node.from);
            const { to } = state.doc.line(lastRow(state, number, state.doc.lineAt(node.to).number));
            if (text.slice(0, node.from - from).trim()) return false;
            if (!ranges || ranges.some((range) => range.from <= to && range.to >= from)) {
                const formatted = formatTable(state.doc.sliceString(from, to));
                if (formatted !== null) found.push({ from, to, formatted });
            }
            return false;
        },
    });
    return found;
}

/**
 * Les modifications qui font de la ligne `before` (à la position `from`) la ligne `after`,
 * où seuls des espaces et des barres diffèrent : le texte des cellules n'est pas touché,
 * un curseur qui s'y trouve y reste.
 */
function rowChanges(before, after, from) {
    const changes = [];
    let i = 0;
    let j = 0;
    while (i < before.length || j < after.length) {
        if (i < before.length && before[i] === after[j]) {
            i++;
            j++;
        } else if (j < after.length && (after[j] === " " || !/\s/.test(before[i] ?? ""))) {
            changes.push({ from: from + i, insert: after[j++] });
        } else {
            changes.push({ from: from + i, to: from + i + 1 });
            i++;
        }
    }
    return changes;
}

function tableChanges(state, { from, to, formatted }) {
    return formatted.split("\n").flatMap((after, row) => {
        const line = state.doc.line(state.doc.lineAt(from).number + row);
        // La ligne de séparation n'a pas de texte à garder.
        if (row === 1) return line.text === after ? [] : [{ from: line.from, to: line.to, insert: after }];
        return rowChanges(line.text, after, line.from);
    });
}

/**
 * Aligne ces tableaux (`findTables`) en une seule modification : un Ctrl+Z annule le tout.
 * Le curseur et la sélection restent à leur place dans le texte.
 */
export function formatTables(view, tables) {
    const { state } = view;
    const changes = state.changes(tables.flatMap((table) => tableChanges(state, table)));
    if (changes.empty) return;
    const move = (pos) => {
        // Au début du texte d'une cellule : y rester quand des espaces s'ajoutent devant.
        const before = state.doc.sliceString(Math.max(0, pos - 1), pos);
        const after = state.doc.sliceString(pos, pos + 1);
        return changes.mapPos(pos, /^[\s|]$/.test(before) && /^[^\s|]$/.test(after) ? 1 : -1);
    };
    const { ranges, mainIndex } = state.selection;
    view.dispatch({
        changes,
        selection: EditorSelection.create(
            ranges.map((range) => EditorSelection.range(move(range.anchor), move(range.head))),
            mainIndex,
        ),
        userEvent: "input.format",
    });
}

/**
 * Le squelette d'un tableau à barres de `columns` colonnes et `rows` lignes (sans l'en-tête),
 * et la position de la première cellule dans ce texte.
 */
export function tableSkeleton(columns, rows) {
    const row = `|${"     |".repeat(columns)}`;
    const lines = [row, `|${" --- |".repeat(columns)}`, ...Array(rows).fill(row)];
    return { text: lines.join("\n"), cursor: 2 };
}

// Lignes d'un tableau : sans retour à la ligne (#402).
const tableLine = Decoration.line({ class: "cm-table-line" });

function tableDecorations(view) {
    const builder = new RangeSetBuilder();
    const { state } = view;
    // Un tableau à cheval sur deux parties visibles n'est décoré qu'une fois, dans l'ordre.
    let decorated = 0;
    for (const { from, to } of view.visibleRanges) {
        syntaxTree(state).iterate({
            from,
            to,
            enter(node) {
                if (node.name !== "Table") return;
                const last = state.doc.lineAt(node.to).number;
                for (let n = Math.max(state.doc.lineAt(node.from).number, decorated + 1); n <= last; n++) {
                    builder.add(state.doc.line(n).from, state.doc.line(n).from, tableLine);
                    decorated = n;
                }
                return false;
            },
        });
    }
    return builder.finish();
}

export const tableLines = ViewPlugin.fromClass(
    class {
        constructor(view) {
            this.decorations = tableDecorations(view);
        }

        update(update) {
            if (update.docChanged || update.viewportChanged || syntaxTree(update.state) !== syntaxTree(update.startState)) {
                this.decorations = tableDecorations(update.view);
            }
        }
    },
    { decorations: (plugin) => plugin.decorations },
);
