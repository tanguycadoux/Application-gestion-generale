// Listes de l'éditeur (#320) : Entrée à la fin d'un élément crée l'élément suivant, comme
// dans VS Code. `@codemirror/lang-markdown`, qui le fait, n'est pas embarqué (il ferait
// charger l'analyseur HTML) : la règle est écrite ici, d'après l'arbre de @lezer/markdown.
import { syntaxTree } from "@codemirror/language";
import { EditorSelection } from "@codemirror/state";

// Une ligne d'élément : retrait, marqueur (`-`, `*`, `+`, `1.`, `2)`), espaces qui suivent.
const ITEM_LINE = /^(\s*)([-*+]|(\d{1,9})([.)]))([ \t]+|$)/;
// Case à cocher en tête du texte de l'élément : `[ ]`, `[x]`.
const TASK_BOX = /^\[[ xX]\](?:[ \t]+|$)/;
// Dans ces blocs, Entrée garde son comportement (une `- ` dans du code n'est pas une liste ;
// les listes d'une citation ne sont pas continuées).
const KEEP_DEFAULT = new Set(["FencedCode", "CodeBlock", "Blockquote"]);

/**
 * La ligne est-elle un élément de liste pour l'analyseur (et pas du code, une citation) ?
 * `repair` : accepte aussi un élément devenu un bloc de code par un retrait trop grand
 * (4 espaces de plus que le texte de son parent), que Maj+Tab doit pouvoir remettre.
 */
function isListItem(state, markerPos, repair = false) {
    let node = syntaxTree(state).resolveInner(markerPos, 1);
    const names = [];
    for (let up = node; up; up = up.parent) names.push(up.name);
    if (repair && names.includes("CodeBlock") && !names.includes("FencedCode") && !names.includes("Blockquote"))
        return true;
    if (node.name !== "ListMark") return false;
    return !names.some((name) => KEEP_DEFAULT.has(name));
}

/**
 * Entrée dans une liste. `false` si ce n'est pas le cas (la commande suivante, retour à la
 * ligne ordinaire, s'en charge) :
 * - élément vide : le marqueur disparaît, on sort de la liste ;
 * - sinon : nouvel élément de même retrait et de même marqueur (numéro suivant pour une liste
 *   numérotée, case vide pour une case à cocher), le texte à droite du curseur en fait partie.
 */
export function continueList(view) {
    const { state } = view;
    const range = state.selection.main;
    if (!range.empty) return false;
    const line = state.doc.lineAt(range.head);
    const match = ITEM_LINE.exec(line.text);
    if (!match) return false;
    const contentFrom = line.from + match[0].length;
    if (range.head < contentFrom || !isListItem(state, line.from + match[1].length)) return false;

    const content = line.text.slice(match[0].length);
    const task = TASK_BOX.exec(content);
    if (task && range.head < contentFrom + task[0].length) return false;

    if (!content.slice(task ? task[0].length : 0).trim()) {
        // Élément vide : la ligne redevient vide.
        view.dispatch({
            changes: { from: line.from, to: line.to },
            selection: EditorSelection.cursor(line.from),
            scrollIntoView: true,
            userEvent: "delete",
        });
        return true;
    }

    const marker = match[3] === undefined ? match[2] : `${Number(match[3]) + 1}${match[4]}`;
    const spacing = match[5] || " ";
    const prefix = `${match[1]}${marker}${spacing}${task ? "[ ] " : ""}`;
    view.dispatch({
        changes: { from: range.head, insert: `\n${prefix}` },
        selection: EditorSelection.cursor(range.head + 1 + prefix.length),
        scrollIntoView: true,
        userEvent: "input",
    });
    return true;
}

/** (retrait, largeur du marqueur et de ses espaces) d'une ligne d'élément, sinon `null`. */
function itemOf(state, line, repair = false) {
    const match = ITEM_LINE.exec(line.text);
    if (!match || !isListItem(state, line.from + match[1].length, repair)) return null;
    return { indent: match[1].length, width: match[0].length - match[1].length };
}

/**
 * Indente (`direction` 1) ou désindente (-1) les éléments de liste de la sélection selon la
 * règle de Pandoc (#229) : une sous-liste commence à la colonne du texte de l'élément au-dessus
 * (2 espaces sous `- `, 3 sous `1. `, 4 sous `10. `). Le retrait par défaut de CodeMirror
 * (2 espaces) donnerait une sous-liste numérotée que Pandoc ne reconnaît pas. `false` si la
 * sélection ne touche aucun élément : le comportement ordinaire s'applique.
 *
 * - **Indenter** : un élément s'imbrique sous l'élément précédent **du même niveau** ; sans
 *   lui (premier élément, ou déjà imbriqué sous son parent), il n'y a rien à faire : un retrait
 *   de plus en ferait un bloc de code.
 * - **Désindenter** : l'élément passe au niveau de son parent ; un élément trop enfoncé (déjà
 *   un bloc de code) est ramené à la colonne du texte de son parent.
 */
export function shiftItems(view, direction) {
    const { state } = view;
    const range = state.selection.main;
    const first = state.doc.lineAt(range.from);
    const last = state.doc.lineAt(range.to);
    // Un élément trop enfoncé (devenu bloc de code) ne se répare que sous un parent : sans
    // lui, c'est du vrai code indenté, qu'on ne transforme pas en liste.
    const valid = itemOf(state, first);
    const target = valid ?? (direction < 0 ? itemOf(state, first, true) : null);
    if (!target) return false;

    let sibling = null;
    let parent = null;
    for (let n = first.number - 1; n >= 1; n--) {
        const above = itemOf(state, state.doc.line(n));
        if (!above || above.indent > target.indent) continue;
        if (above.indent === target.indent) sibling = above;
        else parent = above;
        break;
    }

    if (!valid && !parent) return false;

    let amount;
    if (direction > 0) {
        if (!sibling) return true;
        amount = sibling.width;
    } else if (parent) {
        const child = parent.indent + parent.width;
        amount = target.indent - (target.indent > child ? child : parent.indent);
    } else {
        amount = Math.min(2, target.indent);
    }

    const changes = [];
    for (let n = first.number; n <= last.number; n++) {
        const line = state.doc.line(n);
        if (!line.text.trim()) continue;
        if (direction > 0) {
            changes.push({ from: line.from, insert: " ".repeat(amount) });
        } else {
            const spaces = line.text.length - line.text.trimStart().length;
            const remove = Math.min(amount, spaces);
            if (remove) changes.push({ from: line.from, to: line.from + remove });
        }
    }
    if (!changes.length) return true;
    view.dispatch({ changes, scrollIntoView: true, userEvent: "input.indent" });
    return true;
}

export const listKeymap = [
    { key: "Enter", run: continueList },
    // Tab et Maj+Tab dans une liste ; ailleurs ils gardent leur rôle (passer au champ suivant).
    // Échap puis Tab, ou Ctrl+M, quittent l'éditeur : CodeMirror laisse alors passer Tab.
    { key: "Tab", run: (view) => shiftItems(view, 1) },
    { key: "Shift-Tab", run: (view) => shiftItems(view, -1) },
    { key: "Mod-]", run: (view) => shiftItems(view, 1) },
    { key: "Mod-[", run: (view) => shiftItems(view, -1) },
];
