// Retrait suspendu (#418) : la suite d'une ligne trop longue revient sous son texte, et non au
// bord gauche de l'éditeur. La première ligne ne bouge pas. Pour :
// - un élément de liste, la colonne de son texte, celle de l'imbrication (`lists.js`), case à
//   cocher comprise ;
// - une citation, le texte après ses `>`, et après le marqueur d'une liste qui s'y trouve ;
// - une autre ligne indentée (suite d'un élément, code), son propre retrait.
// En `ch` : l'éditeur est en police à chasse fixe.
import { syntaxTree } from "@codemirror/language";
import { RangeSetBuilder } from "@codemirror/state";
import { Decoration, ViewPlugin } from "@codemirror/view";
import { TASK_BOX, itemOf } from "./lists.js";

const QUOTE = /^(?:[ \t]*>)+[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)?/;
const INDENT = /^ +/;
// Au-delà, la suite n'aurait plus de place dans une fenêtre étroite.
const MAX_COLUMN = 40;
// Marge des lignes de CodeMirror (`.cm-line`), remplacée par le style de la ligne.
const LINE_PADDING = "6px";

/** La colonne du texte d'une ligne, 0 sans retrait à garder. */
export function hangingColumn(state, line) {
    const item = itemOf(state, line);
    if (item) {
        const box = TASK_BOX.exec(line.text.slice(item.column));
        return item.column + (box ? box[0].length : 0);
    }
    return (QUOTE.exec(line.text) ?? INDENT.exec(line.text))?.[0].length ?? 0;
}

// Une décoration par colonne : il y en a peu, elles servent à toutes les lignes.
const decorations = new Map();

function hanging(column) {
    if (!decorations.has(column)) {
        const style = `padding-left: calc(${LINE_PADDING} + ${column}ch); text-indent: -${column}ch`;
        decorations.set(column, Decoration.line({ attributes: { style } }));
    }
    return decorations.get(column);
}

function hangingLines(view) {
    const builder = new RangeSetBuilder();
    const { state } = view;
    let last = 0;
    for (const { from, to } of view.visibleRanges) {
        for (let line = state.doc.lineAt(from); ; line = state.doc.line(line.number + 1)) {
            // Deux parties visibles peuvent se partager une ligne.
            if (line.number > last) {
                last = line.number;
                const column = Math.min(MAX_COLUMN, hangingColumn(state, line));
                // Une tabulation n'a pas de largeur fixe : la ligne reste telle quelle.
                if (column && !line.text.slice(0, column).includes("\t")) {
                    builder.add(line.from, line.from, hanging(column));
                }
            }
            if (line.to >= to || line.number === state.doc.lines) break;
        }
    }
    return builder.finish();
}

export const hangingIndent = ViewPlugin.fromClass(
    class {
        constructor(view) {
            this.decorations = hangingLines(view);
        }

        update(update) {
            if (update.docChanged || update.viewportChanged || syntaxTree(update.state) !== syntaxTree(update.startState)) {
                this.decorations = hangingLines(update.view);
            }
        }
    },
    { decorations: (plugin) => plugin.decorations },
);
