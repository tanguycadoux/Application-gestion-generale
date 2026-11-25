// Mise en forme dans l'éditeur (#434) : paires fermées toutes seules, et Ctrl+B, Ctrl+I, Ctrl+U.
//
// - **Paires** (`closeBracketPairs`) : `closeBrackets` de CodeMirror, sur `PAIRS`. Ni dans un
//   bloc de code délimité, ni dans une formule, écrits tels quels. Un bloc de code indenté en
//   a : l'analyseur en voit là où Pandoc voit une liste.
// - **Gras, italique, souligné** (`toggleMark`) : des bascules, qu'une seule annulation défait.
import { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { isolateHistory } from "@codemirror/commands";
import { ensureSyntaxTree, syntaxTree } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import { hangingColumn } from "./hanging.js";

const PAIRS = ["(", "[", "{", "'", '"', "`"];
// Devant l'un d'eux (ou un blanc, ou la fin de la ligne), une parenthèse se ferme.
const BEFORE = ")]}:;>.,";

// Ce qui compte en cherchant une formule : caractère échappé, code dans la ligne, dollars.
const MATH_TOKEN = /\\.|(`+)[^`]+\1|\$\$?/gs;
// Une formule dans la ligne, comme au rendu (`INLINE_MATH_REGEX`).
const INLINE_MATH = /\$(?![\s$])(?:[^$\\]|\\.)+?(?<!\s)\$(?!\d)/sy;

/** Dans un bloc de code entre ``` ou ~~~, fermé ou non. */
function inCodeBlock(state, pos) {
    for (let node = syntaxTree(state).resolveInner(pos, -1); node; node = node.parent) {
        if (node.name === "FencedCode") return true;
    }
    return false;
}

/** Dans une formule `$…$` ou `$$…$$`, même pas encore fermée ; l'analyseur ne les connaît pas. */
function inMath(state, pos) {
    const line = state.doc.lineAt(pos);
    let first = line;
    while (first.number > 1 && state.doc.line(first.number - 1).text.trim()) {
        first = state.doc.line(first.number - 1);
    }
    const text = state.sliceDoc(first.from, line.to);
    const end = pos - first.from;
    let display = false;
    MATH_TOKEN.lastIndex = 0;
    for (let token; (token = MATH_TOKEN.exec(text)) && token.index < end; ) {
        const stop = MATH_TOKEN.lastIndex;
        if (token[0] === "$$") {
            // Entre les deux dollars d'une formule encore vide.
            if (end < stop) return true;
            display = !display;
        } else if (token[0] === "$" && !display) {
            INLINE_MATH.lastIndex = token.index;
            if (INLINE_MATH.test(text)) {
                if (end < INLINE_MATH.lastIndex) return true;
                MATH_TOKEN.lastIndex = INLINE_MATH.lastIndex;
            } else if (end === stop || /[^\s\d]/.test(text[stop])) {
                // Pas encore fermée ; un montant (« 5 $ », « $5 ») n'en ouvre pas.
                if (!text.slice(stop, end).includes("\n")) return true;
            }
        }
    }
    return display;
}

/** Les paires possibles au curseur ; avec une sélection, toutes : elles l'entourent. */
function pairsAt(state, pos) {
    if (inCodeBlock(state, pos) || inMath(state, pos)) return [];
    if (!state.selection.main.empty) return PAIRS;
    const line = state.doc.lineAt(pos);
    const before = line.text.slice(0, pos - line.from);
    const next = line.text[pos - line.from];
    return PAIRS.filter((mark) => {
        if (mark !== '"' && mark !== "`") return true;
        // Le deuxième de la ligne ferme ; ``` ouvre un bloc, sans paire au bout.
        const opened = before.split(mark).length % 2 === 0;
        return opened ? next === mark : next !== mark && !before.endsWith(mark);
    });
}

export const closeBracketPairs = [
    closeBrackets(),
    // Lu seulement quand `closeBrackets` le demande.
    EditorState.languageData.of((state, pos) => [
        {
            get closeBrackets() {
                return { brackets: pairsAt(state, pos), before: BEFORE };
            },
        },
    ]),
];

const MARKS = [
    { label: "Gras", shortcut: "Ctrl+B", key: "Mod-b", open: "**", close: "**", node: "StrongEmphasis" },
    { label: "Italique", shortcut: "Ctrl+I", key: "Mod-i", open: "*", close: "*", node: "Emphasis" },
    // Ce que lit le rendu (`UnderlineExtension`).
    { label: "Souligné", shortcut: "Ctrl+U", key: "Mod-u", open: "[", close: "]{.underline}" },
];
const UNDERLINED = /(?<!!)\[(?:[^[\]]|\[[^[\]]*\])*(?<close>\]\{ *\.underline *\})/g;
// Dans une sélection de plusieurs lignes, celles-ci restent telles quelles : titres, blocs
// `:::`, délimiteurs de code, tableaux, traits.
const STRUCTURE_LINE = /^\s*(?:#{1,6}\s|:::|`{3}|~{3}|\||(?:[-*_][ \t]*){3,}$)/;
const HEADING_MARK = /^ {0,3}#{1,6}[ \t]+/;

/** Les textes déjà ainsi mis en forme près de `from`-`to` : leurs bornes et celles des marques. */
function markedSpans(state, mark, from, to) {
    const spans = [];
    if (mark.node) {
        const tree = ensureSyntaxTree(state, to, 200) ?? syntaxTree(state);
        tree.iterate({
            from,
            to,
            enter(node) {
                if (node.name !== mark.node) return;
                const { firstChild, lastChild } = node.node;
                spans.push({ from: node.from, openTo: firstChild.to, closeFrom: lastChild.from, to: node.to });
            },
        });
        return spans;
    }
    const line = state.doc.lineAt(from);
    for (const match of line.text.matchAll(UNDERLINED)) {
        const start = line.from + match.index;
        const end = start + match[0].length;
        spans.push({ from: start, openTo: start + 1, closeFrom: end - match.groups.close.length, to: end });
    }
    return spans;
}

const starsAtEnd = (text) => /\**$/.exec(text)[0].length;
const starsAtStart = (text) => /^\**/.exec(text)[0].length;

/** Des astérisques de chaque côté : 1 l'italique, 2 le gras, 3 les deux. */
function hasStars(mark, before, after) {
    const count = Math.min(before, after);
    return count > 2 || count === mark.open.length;
}

/**
 * Les marques juste autour de `from`-`to`, ou à ses deux bouts, lues dans le texte : une paire
 * vide, ou ce que l'analyseur prend pour du code. `null` s'il n'y en a pas.
 */
function marksAround(state, mark, from, to) {
    const { open, close } = mark;
    const line = state.doc.lineAt(from);
    const before = state.sliceDoc(line.from, from);
    const after = state.sliceDoc(to, line.to);
    const inside = state.sliceDoc(from, to);
    const around = mark.node
        ? hasStars(mark, starsAtEnd(before), starsAtStart(after))
        : before.endsWith(open) && after.startsWith(close);
    if (around) return { from: from - open.length, openTo: from, closeFrom: to, to: to + close.length };
    if (inside.length <= open.length + close.length || !mark.node) return null;
    if (!hasStars(mark, starsAtStart(inside), starsAtEnd(inside))) return null;
    return { from, openTo: from + open.length, closeFrom: to - close.length, to };
}

/** Une portion de texte : déjà mise en forme (`remove`), ou à entourer (`wrap`). */
function plan(state, mark, { from, to }, at = null) {
    const spans = markedSpans(state, mark, from, to).filter((span) =>
        at === null ? span.from < to && span.to > from : span.from < at && at < span.to,
    );
    const enclosing = spans.find((span) => span.from <= from && to <= span.to);
    if (enclosing) return { remove: [enclosing] };
    const around = spans.length ? null : marksAround(state, mark, from, to);
    if (around) return { remove: [around] };
    // Ce qui l'est déjà en partie ne fait plus qu'un.
    return {
        remove: spans,
        wrap: {
            from: Math.min(from, ...spans.map((span) => span.from)),
            to: Math.max(to, ...spans.map((span) => span.to)),
        },
    };
}

/**
 * Les portions d'une sélection : une par ligne (une mise en forme ne passe ni d'un paragraphe ni
 * d'un élément à l'autre), sans les blancs des bords ni le marqueur de la ligne.
 */
function portions(state, range) {
    const found = [];
    const first = state.doc.lineAt(range.from).number;
    const last = state.doc.lineAt(range.to).number;
    for (let number = first; number <= last; number++) {
        const line = state.doc.line(number);
        if (first !== last && STRUCTURE_LINE.test(line.text)) continue;
        const column = HEADING_MARK.exec(line.text)?.[0].length ?? hangingColumn(state, line);
        const from = Math.max(range.from, line.from + Math.min(column, line.length));
        const to = Math.min(range.to, line.to);
        const text = state.sliceDoc(from, Math.max(from, to));
        if (!text.trim()) continue;
        found.push({
            from: from + text.length - text.trimStart().length,
            to: from + text.trimEnd().length,
        });
    }
    return found;
}

/**
 * Après le changement, la sélection : le même texte, entre les marques, ou marques comprises si
 * elle n'a pas été entourée d'un seul tenant.
 */
function movedSelection(range, set, word, plans, emptyPair) {
    if (emptyPair) return EditorSelection.cursor(set.mapPos(range.head, -1) + emptyPair);
    if (range.empty) return EditorSelection.cursor(set.mapPos(range.head, word?.from === range.head ? 1 : -1));
    const [{ wrap, remove }] = plans;
    const whole =
        plans.length === 1 &&
        wrap?.from <= range.from &&
        range.to <= wrap.to &&
        !remove.some((span) => span.from === range.from || span.to === range.to);
    const from = set.mapPos(range.from, whole ? 1 : -1);
    const to = set.mapPos(range.to, whole ? -1 : 1);
    return range.anchor <= range.head ? EditorSelection.range(from, to) : EditorSelection.range(to, from);
}

/** Met en forme, ou en défait, la sélection ou le mot du curseur ; ailleurs, une paire vide. */
function toggleMark(view, mark) {
    const { state } = view;
    const { open, close } = mark;
    // L'éditeur n'a qu'une sélection.
    const range = state.selection.main;
    const word = range.empty ? state.wordAt(range.head) : null;
    const plans = range.empty
        ? [plan(state, mark, word ?? range, range.head)]
        : portions(state, range).map((portion) => plan(state, mark, portion));
    const removing = plans.every(({ wrap }) => !wrap);
    // Sans doublon : deux lignes peuvent être dans le même texte mis en forme.
    const changes = new Map();
    const change = (from, to, insert) => changes.set(`${from} ${to} ${insert}`, { from, to, insert });
    let emptyPair = 0;
    for (const { remove, wrap } of plans) {
        if (!wrap && !removing) continue;
        for (const span of remove) {
            change(span.from, span.openTo, "");
            change(span.closeFrom, span.to, "");
        }
        if (!wrap) continue;
        if (wrap.from === wrap.to) emptyPair = open.length;
        change(wrap.from, wrap.from, emptyPair ? open + close : open);
        if (!emptyPair) change(wrap.to, wrap.to, close);
    }
    if (changes.size) {
        const set = state.changes([...changes.values()]);
        view.dispatch({
            changes: set,
            selection: EditorSelection.create([movedSelection(range, set, word, plans, emptyPair)]),
            scrollIntoView: true,
            userEvent: "input",
            annotations: isolateHistory.of("full"),
        });
    }
    // Toujours prise : Ctrl+U ouvrirait le code source de la page, Ctrl+B les marque-pages.
    return true;
}

/** À placer avant les raccourcis de CodeMirror, qui prend Ctrl+I et Ctrl+U. */
export const formattingKeymap = [
    ...closeBracketsKeymap,
    ...MARKS.map((mark) => ({
        key: mark.key,
        run: (view) => toggleMark(view, mark),
        preventDefault: true,
    })),
];

/** Les entrées du sous-menu « Mise en forme » (`entries`, `editor_menu.js`). */
export function formattingEntries(view) {
    return MARKS.map((mark) => ({
        label: mark.label,
        shortcut: mark.shortcut,
        run: () => toggleMark(view, mark),
    }));
}
