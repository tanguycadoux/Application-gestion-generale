// Listes de l'éditeur (#320, #325) : Entrée à la fin d'un élément crée l'élément suivant,
// Tab et Maj+Tab indentent, comme dans VS Code. `@codemirror/lang-markdown`, qui le fait,
// n'est pas embarqué (il ferait charger l'analyseur HTML) : la règle est écrite ici.
//
// Les marqueurs sont ceux de Pandoc (extension `fancy_lists`), comme dans `qmd/lists.py`, dont
// `parseMarker` est le pendant : `-` `*` `+`, `1.` `1)` `(1)`, `a.` `A)` `(a)`, `i.` `iv)`,
// `#.`, `(@)`. L'analyseur de @lezer/markdown ne connaît que les puces et `1.` `1)` : pour les
// autres, la ligne est un élément si Pandoc en ferait un (voir `eligible`).
import { syntaxTree } from "@codemirror/language";
import { EditorSelection } from "@codemirror/state";

// Une ligne d'élément, avant validation : retrait, marqueur, espaces qui suivent.
const ITEM_LINE = /^(\s*)([-*+]|(?:\d+|[A-Za-z]+|#)[.)]|\((?:\d+|[A-Za-z]+|@[\w-]*)\))([ \t]+|$)/;
// Case à cocher en tête du texte de l'élément : `[ ]`, `[x]`.
const TASK_BOX = /^\[[ xX]\](?:[ \t]+|$)/;
const HEADING_LINE = /^#{1,6}(\s|$)/;
// Dans ces blocs, Entrée garde son comportement (une `- ` dans du code n'est pas une liste ;
// les listes d'une citation ne sont pas continuées).
const KEEP_DEFAULT = new Set(["FencedCode", "CodeBlock", "Blockquote"]);

const ROMAN = /^m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$/;
const ROMAN_PARTS = [
    ["m", 1000], ["cm", 900], ["d", 500], ["cd", 400], ["c", 100], ["xc", 90],
    ["l", 50], ["xl", 40], ["x", 10], ["ix", 9], ["v", 5], ["iv", 4], ["i", 1],
];
const ROMAN_VALUES = { i: 1, v: 5, x: 10, l: 50, c: 100, d: 500, m: 1000 };
const MAX_DIGITS = 9;

/** Valeur d'un chiffre romain en minuscules, `null` s'il n'est pas valide. */
function romanValue(text) {
    if (!text || !ROMAN.test(text)) return null;
    let total = 0;
    for (let i = 0; i < text.length; i++) {
        const value = ROMAN_VALUES[text[i]];
        total += (ROMAN_VALUES[text[i + 1]] ?? 0) > value ? -value : value;
    }
    return total;
}

function toRoman(number) {
    if (!Number.isInteger(number) || number < 1 || number > 3999) return null;
    let rest = number;
    let text = "";
    for (const [letters, value] of ROMAN_PARTS) {
        while (rest >= value) {
            text += letters;
            rest -= value;
        }
    }
    return text;
}

/**
 * Lit un marqueur d'élément (pendant de `parse_marker` de `qmd/lists.py`) ; `null` si ce n'en
 * est pas un pour Pandoc. `context` : le marqueur de l'élément précédent de la même liste, qui
 * décide des lettres ambiguës (`i.` reste la lettre i dans `a.` `b.` `i.`).
 */
export function parseMarker(marker, space, context = null) {
    const make = (kind, upper, delimiter, value) => ({ kind, upper, delimiter, value });
    if (marker === "-" || marker === "*" || marker === "+") return make("bullet", false, "", 1);
    let delimiter;
    let body;
    if (marker.startsWith("(")) {
        if (!marker.endsWith(")")) return null;
        delimiter = "()";
        body = marker.slice(1, -1);
    } else {
        delimiter = marker.slice(-1);
        body = marker.slice(0, -1);
    }
    if (body.startsWith("@")) return delimiter === "()" ? make("example", false, "()", 1) : null;
    if (body === "#") return delimiter === "()" ? null : make("auto", false, delimiter, 1);
    if (/^\d+$/.test(body)) {
        return body.length > MAX_DIGITS ? null : make("decimal", false, delimiter, Number(body));
    }
    if (!/^[A-Za-z]+$/.test(body)) return null;
    const upper = body === body.toUpperCase();
    if (!upper && body !== body.toLowerCase()) return null;
    // Une majuscule seule suivie d'un point est une initiale (« A. Dupont ») : Pandoc veut
    // deux espaces au moins.
    if (body.length === 1 && upper && delimiter === "." && space.length < 2) return null;

    const low = body.toLowerCase();
    const roman = romanValue(low);
    let kind = null;
    if (context && context.upper === upper) {
        if (context.kind === "roman" && roman !== null) kind = "roman";
        else if (context.kind === "alpha" && low.length === 1) kind = "alpha";
    }
    if (kind === null) {
        if (low === "i" || (low.length > 1 && roman !== null)) kind = "roman";
        else if (low.length === 1) kind = "alpha";
        else return null;
    }
    const value = kind === "roman" && roman !== null ? roman : low.charCodeAt(0) - 96;
    return make(kind, upper, delimiter, value);
}

/** Deux éléments de même style sont de la même liste ; sinon Pandoc en commence une autre. */
const styleOf = (marker) => `${marker.kind}|${marker.upper}|${marker.delimiter}`;
// L'analyseur de @lezer/markdown reconnaît les puces et `1.` `1)` : `ListMark`.
const knownToParser = (marker) =>
    marker.kind === "bullet" || (marker.kind === "decimal" && marker.delimiter !== "()");

/** Texte du marqueur de rang `value` dans le style de `marker` ; `null` s'il n'existe pas. */
function markerText(marker, value) {
    let body;
    if (marker.kind === "decimal") body = String(value);
    else if (marker.kind === "alpha") body = value >= 1 && value <= 26 ? String.fromCharCode(96 + value) : null;
    else if (marker.kind === "roman") body = toRoman(value);
    else return null;
    if (body === null) return null;
    if (marker.upper) body = body.toUpperCase();
    return marker.delimiter === "()" ? `(${body})` : `${body}${marker.delimiter}`;
}

/** Les espaces après un marqueur : deux au moins pour une initiale (`A.`), sinon inchangés. */
function spacingFor(text, spacing) {
    return /^[A-Z]\.$/.test(text) && spacing.length < 2 ? "  " : spacing || " ";
}

/** (retrait, marqueur et espaces) d'une ligne qui a la forme d'un élément, sinon `null`. */
function rawItem(line) {
    const match = ITEM_LINE.exec(line.text);
    if (!match) return null;
    return {
        indent: match[1].length,
        text: match[2],
        spacing: match[3],
        width: match[0].length - match[1].length,
    };
}

/**
 * Le marqueur d'une ligne, lu avec le contexte de sa liste : les éléments précédents du même
 * retrait, du premier au dernier. Une ligne de texte au même retrait, ou moins, ouvre la liste.
 */
function markerOf(state, line, raw) {
    const chain = [];
    for (let n = line.number - 1; n >= 1; n--) {
        const above = state.doc.line(n);
        if (!above.text.trim()) continue;
        const aboveRaw = rawItem(above);
        if (aboveRaw && aboveRaw.indent === raw.indent && parseMarker(aboveRaw.text, aboveRaw.spacing)) {
            chain.push(aboveRaw);
            continue;
        }
        if (above.text.length - above.text.trimStart().length > raw.indent) continue;
        break;
    }
    let context = null;
    for (const above of chain.reverse()) {
        context = parseMarker(above.text, above.spacing, context) ?? context;
    }
    return parseMarker(raw.text, raw.spacing, context);
}

/**
 * Pandoc fait d'un marqueur que l'analyseur ne connaît pas (`a.`, `(1)`, `#.`…) un élément de
 * liste après une ligne vide, un titre, un autre élément ou en début de texte : pas collé à un
 * paragraphe.
 */
function eligible(state, line) {
    if (line.number === 1) return true;
    const above = state.doc.line(line.number - 1);
    if (!above.text.trim() || HEADING_LINE.test(above.text)) return true;
    const aboveRaw = rawItem(above);
    if (aboveRaw && parseMarker(aboveRaw.text, aboveRaw.spacing)) return true;
    return above.text.startsWith(" ");
}

/**
 * La ligne est-elle un élément de liste (et pas du code, une citation) ? `repair` : accepte
 * aussi un élément devenu un bloc de code par un retrait trop grand (4 espaces de plus que le
 * texte de son parent), que Maj+Tab doit pouvoir remettre.
 */
function isListItem(state, line, raw, marker, repair) {
    const names = [];
    for (let node = syntaxTree(state).resolveInner(line.from + raw.indent, 1); node; node = node.parent) {
        names.push(node.name);
    }
    if (repair && names.includes("CodeBlock") && !names.includes("FencedCode") && !names.includes("Blockquote")) {
        return true;
    }
    if (names.some((name) => KEEP_DEFAULT.has(name))) return false;
    if (knownToParser(marker)) return names[0] === "ListMark";
    return eligible(state, line);
}

/** L'élément d'une ligne : retrait, largeur du marqueur, marqueur lu ; sinon `null`. */
function itemOf(state, line, repair = false) {
    const raw = rawItem(line);
    if (!raw) return null;
    const marker = markerOf(state, line, raw);
    if (!marker || !isListItem(state, line, raw, marker, repair)) return null;
    return { ...raw, marker };
}

/**
 * Entrée dans une liste. `false` si ce n'est pas le cas (la commande suivante, retour à la
 * ligne ordinaire, s'en charge) :
 * - élément vide : le marqueur disparaît, on sort de la liste ;
 * - sinon : nouvel élément de même retrait et de même marqueur (suivant dans la liste : numéro,
 *   lettre ou chiffre romain ; case vide pour une case à cocher), le texte à droite du curseur
 *   en fait partie.
 */
export function continueList(view) {
    const { state } = view;
    const range = state.selection.main;
    if (!range.empty) return false;
    const line = state.doc.lineAt(range.head);
    const item = itemOf(state, line);
    if (!item) return false;
    const contentFrom = line.from + item.indent + item.width;
    if (range.head < contentFrom) return false;

    const content = line.text.slice(item.indent + item.width);
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

    const next = markerText(item.marker, item.marker.value + 1);
    let text = item.text;
    if (item.marker.kind === "example") text = "(@)";
    else if (next !== null) text = next;
    const prefix = `${" ".repeat(item.indent)}${text}${spacingFor(text, item.spacing)}${task ? "[ ] " : ""}`;
    view.dispatch({
        changes: { from: range.head, insert: `\n${prefix}` },
        selection: EditorSelection.cursor(range.head + 1 + prefix.length),
        scrollIntoView: true,
        userEvent: "input",
    });
    return true;
}

/**
 * Rang du marqueur de l'élément déplacé au retrait `indent`, selon sa nouvelle place : 1 s'il
 * ouvre une liste (Pandoc commence une liste numérotée au numéro de son premier élément, un
 * `2.` imbriqué ferait donc partir la sous-liste à 2 ; `a.` et `i.` de même), sinon le suivant
 * de l'élément précédent du niveau, s'il est du même style.
 */
function startValue(state, lineNumber, indent, marker) {
    for (let n = lineNumber - 1; n >= 1; n--) {
        const above = itemOf(state, state.doc.line(n));
        if (!above || above.indent > indent) continue;
        if (above.indent < indent) return 1;
        return styleOf(above.marker) === styleOf(marker) ? above.marker.value + 1 : 1;
    }
    return 1;
}

/**
 * Indente (`direction` 1) ou désindente (-1) les éléments de liste de la sélection selon la
 * règle de Pandoc (#229) : une sous-liste commence à la colonne du texte de l'élément au-dessus
 * (2 espaces sous `- `, 3 sous `1. `, 4 sous `10. ` ou `(a) `). Le retrait par défaut de
 * CodeMirror (2 espaces) donnerait une sous-liste numérotée que Pandoc ne reconnaît pas. `false`
 * si la sélection ne touche aucun élément : le comportement ordinaire s'applique.
 *
 * - **Indenter** : un élément s'imbrique sous l'élément précédent **du même niveau** ; sans
 *   lui (premier élément, ou déjà imbriqué sous son parent), il n'y a rien à faire : un retrait
 *   de plus en ferait un bloc de code.
 * - **Désindenter** : l'élément passe au niveau de son parent ; un élément trop enfoncé (déjà
 *   un bloc de code) est ramené à la colonne du texte de son parent.
 * - Les éléments numérotés du niveau déplacé sont renumérotés (1, a, i…) à partir de leur
 *   nouvelle place.
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
        if (above.indent < target.indent) {
            parent = above;
            break;
        }
        // Indenter : on s'imbrique sous le frère juste au-dessus. Désindenter : les frères
        // ne comptent pas, on cherche le parent au-delà.
        sibling ??= above;
        if (direction > 0) break;
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

    // Les éléments numérotés du niveau déplacé sont renumérotés à partir de leur nouvelle
    // place ; ceux des sous-niveaux gardent leurs numéros (relatifs à leur propre liste).
    const moved = direction > 0 ? amount : -Math.min(amount, target.indent);
    let value = startValue(state, first.number, target.indent + moved, target.marker);

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
        const item = itemOf(state, line, direction < 0);
        if (item && item.indent === target.indent && styleOf(item.marker) === styleOf(target.marker)) {
            const text = markerText(item.marker, value);
            if (text !== null && text !== item.text) {
                const from = line.from + item.indent;
                changes.push({
                    from,
                    to: from + item.text.length + item.spacing.length,
                    insert: text + spacingFor(text, item.spacing),
                });
            }
            value += 1;
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
