// Lignes et colonnes d'un tableau à barres (#435) ; `tables.js` en garde le format.
//
// - Une **commande** est une fonction pure : d'un tableau `{ rows, columns }` et d'une cellule
//   `{ row, column }`, elle donne les nouvelles lignes et la cellule du curseur, ou `null` si
//   elle est impossible. `rows` est le tableau en cellules : la ligne 0 est l'en-tête, la
//   ligne 1 la séparation, toutes ont `columns` cellules.
// - `editTable` l'applique au texte d'un tableau, qui en sort formaté (`formatTable`).
// - `runTableCommand` l'applique au tableau de l'éditeur, en une seule modification ; un
//   Ctrl+Z l'annule, donc rien n'est demandé avant de perdre du contenu.
// - `tableEntries` en fait les entrées du menu du clic droit (`editor_menu.js`).
//
// La légende n'est pas dans le tableau (`findTables`) : elle n'est pas touchée.
import { isolateHistory } from "@codemirror/commands";
import { EditorSelection } from "@codemirror/state";
import { TABLE_FIELDS, countsForm } from "./block_templates.js";
import { cellRanges, findTables, formatTable, hasEdges, splitTable } from "./tables.js";

// L'en-tête et la séparation.
const HEAD = 2;

/** La cellule ajoutée à la ligne `row`. */
const blank = (row) => (row === 1 ? "---" : "");

/** Le tableau `text` en cellules : une ligne trop courte est complétée. */
function parseTable(text) {
    const cells = splitTable(text.split("\n"));
    const columns = Math.max(...cells.map((row) => row.length));
    const rows = cells.map((row, index) =>
        Array.from({ length: columns }, (_, column) => row[column] ?? blank(index)),
    );
    return { rows, columns };
}

/** Les nombres du formulaire : colonnes, et lignes sans l'en-tête. */
function dimensions({ rows, columns }) {
    return [columns, rows.length - HEAD];
}

const insertRow = (after) => ({ rows, columns }, { row }) => {
    // Rien avant l'en-tête ; après lui ou la séparation, la première ligne du corps.
    if (!after && row < HEAD) return null;
    const at = after ? Math.max(row + 1, HEAD) : row;
    return { rows: rows.toSpliced(at, 0, Array(columns).fill("")), cell: { row: at, column: 0 } };
};

const insertColumn = (after) => ({ rows }, { column }) => {
    const at = after ? column + 1 : column;
    return {
        rows: rows.map((cells, row) => cells.toSpliced(at, 0, blank(row))),
        cell: { row: 0, column: at },
    };
};

export const insertRowBefore = insertRow(false);
export const insertRowAfter = insertRow(true);
export const insertColumnBefore = insertColumn(false);
export const insertColumnAfter = insertColumn(true);

export function deleteRow({ rows }, cell) {
    return cell.row < HEAD ? null : { rows: rows.toSpliced(cell.row, 1), cell };
}

export function deleteColumn({ rows, columns }, cell) {
    return columns === 1 ? null : { rows: rows.map((cells) => cells.toSpliced(cell.column, 1)), cell };
}

/** Ajoute des colonnes et des lignes vides à la fin, ou retire les dernières. */
export const resizeTable = (columns, bodyRows) => ({ rows }, cell) => ({
    rows: Array.from({ length: HEAD + bodyRows }, (_, row) =>
        Array.from({ length: columns }, (_, column) => rows[row]?.[column] ?? blank(row)),
    ),
    cell,
});

/** La position du texte de la cellule `cell` dans le tableau formaté, ou près d'elle. */
function cellPosition(text, { row, column }) {
    const lines = text.split("\n");
    let index = Math.min(row, lines.length - 1);
    // Il n'y a rien à écrire dans la séparation.
    if (index === 1) index = 0;
    const ranges = cellRanges(lines[index]);
    const { from, to } = ranges[Math.min(column, ranges.length - 1)];
    const cell = lines[index].slice(from, to);
    const start = lines.slice(0, index).join("\n").length + (index ? 1 : 0);
    return start + from + (cell.trim() ? cell.length - cell.trimStart().length : 1);
}

/** Le tableau `text` modifié et la position du curseur, `null` si c'est impossible. */
export function editTable(text, cell, command) {
    const edited = command(parseTable(text), cell);
    if (!edited) return null;
    const indent = /^\s*/.exec(text)[0];
    const formatted = formatTable(edited.rows.map((cells) => `${indent}| ${cells.join(" | ")} |`).join("\n"));
    return { text: formatted, cursor: cellPosition(formatted, edited.cell) };
}

/**
 * Le tableau à barres qui contient `pos` : `{ from, to, text, cell }`, où `cell` est la
 * cellule à cette position ; sinon `null` (dans sa légende, par exemple).
 */
export function tableCell(state, pos) {
    const [table] = findTables(state, [{ from: pos, to: pos }]);
    if (!table) return null;
    const { from, to } = table;
    const line = state.doc.lineAt(pos);
    const header = state.doc.lineAt(from);
    const row = line.number - header.number;
    const ranges = cellRanges(line.text, hasEdges(header.text) || row === 1);
    const column = ranges.findIndex((range) => pos - line.from <= range.to);
    return {
        from,
        to,
        text: state.sliceDoc(from, to),
        cell: { row, column: column < 0 ? ranges.length - 1 : column },
    };
}

/** Applique une commande à la cellule à la position `pos` ; faux si c'est impossible. */
export function runTableCommand(view, pos, command) {
    const target = tableCell(view.state, pos);
    const edited = target && editTable(target.text, target.cell, command);
    if (!edited) return false;
    const { from, to, text } = target;
    view.dispatch({
        changes: edited.text === text ? [] : { from, to, insert: edited.text },
        selection: EditorSelection.cursor(from + edited.cursor),
        scrollIntoView: true,
        userEvent: "input.table",
        annotations: isolateHistory.of("full"),
    });
    return true;
}

/** Les entrées du menu pour un clic à la position `pos` ; `showForm` y affiche un formulaire. */
export function tableEntries(view, pos, showForm) {
    const target = tableCell(view.state, pos);
    if (!target) return [];
    const entry = (label, command) => ({
        label,
        enabled: editTable(target.text, target.cell, command) !== null,
        run: () => runTableCommand(view, pos, command),
    });
    const current = dimensions(parseTable(target.text));
    const form = {
        label: "Dimensions…",
        action: "Appliquer",
        // L'en-tête peut rester seul ; un grand tableau garde sa taille.
        fields: TABLE_FIELDS.map((field, index) => ({
            ...field,
            value: current[index],
            min: field.name === "rows" ? 0 : field.min,
            max: Math.max(field.max, current[index]),
        })),
        run: (counts) => runTableCommand(view, pos, resizeTable(...counts)),
    };
    return [
        entry("Insérer une ligne avant", insertRowBefore),
        entry("Insérer une ligne après", insertRowAfter),
        entry("Insérer une colonne avant", insertColumnBefore),
        entry("Insérer une colonne après", insertColumnAfter),
        { separator: true },
        entry("Supprimer la ligne", deleteRow),
        entry("Supprimer la colonne", deleteColumn),
        { separator: true },
        { label: form.label, keepOpen: true, run: () => showForm(countsForm(form)) },
    ];
}
