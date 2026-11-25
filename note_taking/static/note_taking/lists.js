// Listes de l'éditeur (#320, #325) : Entrée à la fin d'un élément crée l'élément suivant,
// Tab et Maj+Tab indentent, comme dans VS Code. `@codemirror/lang-markdown`, qui le fait,
// n'est pas embarqué (il ferait charger l'analyseur HTML) : la règle est écrite ici.
//
// Les marqueurs sont ceux de Pandoc (extension `fancy_lists`), comme dans `qmd/lists.py`, dont
// `parseMarker` est le pendant : `-` `*` `+`, `1.` `1)` `(1)`, `a.` `A)` `(a)`, `i.` `iv)`,
// `#.`, `(@)`. L'analyseur de @lezer/markdown ne connaît que les puces et `1.` `1)` : pour les
// autres, et sous eux, la ligne est un élément si Pandoc en ferait un (voir `scanLists`).
import { syntaxTree } from "@codemirror/language";
import { EditorSelection, RangeSetBuilder } from "@codemirror/state";
import { Decoration, ViewPlugin } from "@codemirror/view";

// Une ligne d'élément, avant validation : retrait, marqueur, espaces qui suivent.
const ITEM_LINE = /^(\s*)([-*+]|(?:\d+|[A-Za-z]+|#)[.)]|\((?:\d+|[A-Za-z]+|@[\w-]*)\))([ \t]+|$)/;
// Case à cocher en tête du texte de l'élément : `[ ]`, `[x]`.
export const TASK_BOX = /^\[[ xX]\](?:[ \t]+|$)/;
const HEADING_LINE = /^#{1,6}(\s|$)/;
const RULE_LINE = /^\s*([-*])(?:[ \t]*\1){2,}[ \t]*$/;
const FENCE_LINE = /^\s*(`{3,}|~{3,})([^`]*)$/;
const DIV_LINE = /^\s*:::/;
// À 4 espaces au-delà du texte du parent, un marqueur n'ouvre plus d'élément (`qmd/lists.py`).
const CODE_INDENT = 4;
// Dans ces blocs, Entrée garde son comportement (une `- ` dans du code n'est pas une liste ;
// les listes d'une citation ne sont pas continuées).
const KEEP_DEFAULT = new Set(["FencedCode", "Blockquote"]);

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
function rawItem(text) {
    const match = ITEM_LINE.exec(text);
    if (!match || RULE_LINE.test(text)) return null;
    return {
        indent: match[1].length,
        text: match[2],
        spacing: match[3],
        width: match[0].length - match[1].length,
    };
}

/** Colonne du texte d'un élément : pendant de `text_column` (`qmd/lists.py`). */
function textColumn(raw) {
    const space = raw.spacing.length;
    return raw.indent + raw.text.length + (space > 0 && space <= CODE_INDENT ? space : 1);
}

// Par texte de la note (immuable) : il n'est lu qu'une fois pour toutes ses lignes.
const scans = new WeakMap();

/**
 * Les lignes de marqueur de la note, lues comme le rendu (pendant de
 * `PandocListsPreprocessor`, `rendering/lists.py`) : numéro de ligne → élément, avec
 * - `open` : les éléments ouverts au-dessus, du plus extérieur au plus intérieur ;
 * - `level` : le nombre de ceux dont la ligne atteint le texte. Le parent est donc
 *   `open[level - 1]`, l'élément précédent du même niveau `open[level]` ;
 * - `valid` : Pandoc en ferait un élément ;
 * - `end` : sa dernière ligne, suites et sous-listes comprises ;
 * - `pandoc` : la liste a un marqueur que l'analyseur ne connaît pas, à cette ligne ou au-dessus.
 *
 * Un bloc de code délimité est sauté, un bloc `:::` ferme les listes.
 */
function scanLists(doc) {
    if (scans.has(doc)) return scans.get(doc);
    const found = new Map();
    let open = [];
    let fence = null;
    let blank = true;
    let afterHeading = false;
    let number = 0;
    for (const text of doc.iterLines()) {
        number += 1;
        const indent = text.length - text.trimStart().length;
        if (text.trim()) {
            for (const item of open) if (indent >= item.column) item.end = number;
        }
        const delimiter = FENCE_LINE.exec(text);
        if (fence) {
            if (delimiter?.[1].startsWith(fence) && !delimiter[2].trim()) fence = null;
            continue;
        }
        const div = DIV_LINE.test(text);
        if (div || (delimiter && indent === 0)) open = [];
        if (delimiter) fence = delimiter[1];
        if (div || delimiter || !text.trim()) {
            blank = true;
            afterHeading = false;
            continue;
        }
        const heading = HEADING_LINE.test(text);
        const level = open.filter((item) => indent >= item.column).length;
        const raw = rawItem(text);
        const marker = raw && parseMarker(raw.text, raw.spacing, open[level]?.marker);
        let valid = false;
        if (marker) {
            const container = level ? open[level - 1].column : 0;
            // Les marqueurs de Pandoc ne peuvent pas interrompre un paragraphe.
            valid =
                indent < container + CODE_INDENT &&
                (knownToParser(marker) || blank || afterHeading || open.length > 0);
            const pandoc = !knownToParser(marker) || open.some((item) => item.pandoc);
            const item = { ...raw, marker, column: textColumn(raw), level, open, valid, pandoc, end: number };
            found.set(number, item);
            if (valid) open = [...open.slice(0, level), item];
        }
        if (!valid && !level && (blank || heading)) open = [];
        blank = false;
        afterHeading = heading;
    }
    scans.set(doc, found);
    return found;
}

/** Les nœuds de l'arbre au marqueur de la ligne, du plus intérieur au plus extérieur. */
function nodeNames(state, line, item) {
    const names = [];
    for (let node = syntaxTree(state).resolveInner(line.from + item.indent, 1); node; node = node.parent) {
        names.push(node.name);
    }
    return names;
}

/**
 * L'élément d'une ligne (voir `scanLists`), `null` si ce n'en est pas un (ou du code, une
 * citation). L'arbre de l'analyseur décide, sauf pour un marqueur qu'il ne connaît pas et pour
 * les lignes qui suivent dans la même liste (#417) : pour lui, `A.  ` est du texte et le `-`
 * en dessous est mal placé. `repair` : accepte aussi un élément devenu un bloc de code par un
 * retrait trop grand (4 espaces de plus que le texte de son parent), que Maj+Tab doit remettre.
 */
export function itemOf(state, line, repair = false) {
    const item = scanLists(state.doc).get(line.number);
    if (!item) return null;
    const names = nodeNames(state, line, item);
    if (names.some((name) => KEEP_DEFAULT.has(name))) return null;
    if (repair && names.includes("CodeBlock")) return item;
    const valid = item.pandoc ? item.valid : names[0] === "ListMark";
    return valid ? item : null;
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
 * Rang, dans le style de `marker`, du marqueur de l'élément déplacé au niveau `level`, selon sa
 * nouvelle place : 1 s'il ouvre une liste (Pandoc commence une liste numérotée au numéro de son
 * premier élément, un `2.` imbriqué ferait donc partir la sous-liste à 2 ; `a.` et `i.` de même),
 * sinon le suivant de l'élément précédent du niveau, s'il est du même style.
 */
function startValue(target, level, marker) {
    const above = target.open[level];
    return above && styleOf(above.marker) === styleOf(marker) ? above.marker.value + 1 : 1;
}

/**
 * L'élément dont le marqueur sert de modèle à `target`, déplacé au niveau `level` (#419) : parmi
 * ceux qui y seront ses frères, au-dessus et en dessous, le plus proche (en nombre d'éléments,
 * au-dessus d'abord) de ceux du style majoritaire. Les `(@)` ne comptent pas. `null` si le
 * niveau est vide.
 */
function levelModel(doc, target, level) {
    const above = [];
    for (let item = target.open[level]; item; item = item.open[level]) above.push(item);
    const below = [];
    let previous = target.open[level];
    for (const item of scanLists(doc).values()) {
        if (!item.valid || item.level !== level) continue;
        if (item.open[level - 1] !== target.open[level - 1] || item.open[level] !== previous) continue;
        below.push(item);
        previous = item;
    }
    const [over, under] = [above, below].map((items) => items.filter(({ marker }) => marker.kind !== "example"));
    const near = [];
    for (let i = 0; i < Math.max(over.length, under.length); i++) near.push(over[i], under[i]);
    const siblings = near.filter(Boolean);
    const counts = new Map();
    for (const { marker } of siblings) counts.set(styleOf(marker), (counts.get(styleOf(marker)) ?? 0) + 1);
    const most = Math.max(...counts.values());
    return siblings.find(({ marker }) => counts.get(styleOf(marker)) === most) ?? null;
}

/** Marqueur et espaces de `item`, au rang `value` dans le style de `model` (`null` : le sien). */
function restyle(item, model, value) {
    const text = markerText((model ?? item).marker, value) ?? (model ?? item).text;
    if (text === item.text) return item;
    // Au-delà de 4 espaces, la suite est du code : on n'y touche pas, et on n'en crée pas.
    const usable = [item, model].every((of) => of?.spacing && of.spacing.length <= CODE_INDENT);
    return { ...item, text, spacing: spacingFor(text, (usable ? model : item).spacing) };
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
 * - Les éléments du niveau déplacé prennent le style du niveau où ils arrivent (`levelModel`,
 *   #419), et sont renumérotés (1, a, i…) à partir de leur nouvelle place.
 * - Les suites et les sous-listes d'un élément déplacé restent alignées sur son texte, même hors
 *   de la sélection ; ce qui suivait dans le parent et devient sa suite s'y aligne aussi.
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

    // Indenter : on s'imbrique sous le frère juste au-dessus. Désindenter : on cherche le parent.
    const sibling = target.open[target.level];
    const parent = target.open[target.level - 1];
    if (!valid && !parent) return false;

    let amount;
    let level = target.level;
    if (direction > 0) {
        if (!sibling) return true;
        amount = sibling.column - target.indent;
        level += 1;
    } else if (parent) {
        const realign = target.indent > parent.column;
        amount = target.indent - (realign ? parent.column : parent.indent);
        if (!realign) level -= 1;
    } else {
        amount = Math.min(2, target.indent);
    }

    // Les éléments du niveau déplacé changent de style et de numéro ; ceux des sous-niveaux
    // gardent les leurs (relatifs à leur propre liste).
    const changesLevel = level !== target.level;
    const model = changesLevel || !valid ? levelModel(state.doc, target, level) : null;
    const style = styleOf(target.marker);
    let value = startValue(target, level, (model ?? target).marker);

    const changes = [];
    const move = (line, by) => {
        if (!line.text.trim()) return;
        if (by > 0) changes.push({ from: line.from, insert: " ".repeat(by) });
        const remove = Math.min(-by, line.text.length - line.text.trimStart().length);
        if (remove > 0) changes.push({ from: line.from, to: line.from + remove });
    };

    let end = last.number;
    for (let n = first.number; n <= last.number; n++) {
        end = Math.max(end, scanLists(state.doc).get(n)?.end ?? 0);
    }
    let shift = 0;
    let column = 0;
    for (let n = first.number; n <= end; n++) {
        const line = state.doc.line(n);
        const item = itemOf(state, line, !valid);
        if (!item || item.level > target.level) {
            move(line, shift);
            continue;
        }
        shift = direction > 0 ? amount : -Math.min(amount, item.indent);
        move(line, shift);
        if (item.level < target.level) continue;
        if (item.marker.kind !== "example" && (model || styleOf(item.marker) === style)) {
            const next = restyle(item, model, value);
            value += 1;
            if (next !== item) {
                const from = line.from + item.indent;
                changes.push({ from, to: from + item.width, insert: next.text + next.spacing });
                // Le texte s'est décalé avec la largeur du marqueur : ce qui suit aussi.
                shift += textColumn(next) - item.column;
            }
        }
        column = item.column + shift;
    }
    if (direction < 0 && changesLevel) {
        for (let n = end + 1; n <= parent.end; n++) move(state.doc.line(n), column - parent.column);
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

// Marqueurs que l'analyseur ne connaît pas (#328) : `a.`, `(1)`, `#.`, `iv)`… Pour lui, ces
// lignes sont des paragraphes ; ils sont colorés, et les marqueurs sous eux (#417), comme les
// `ListMark` (`cm-pandoc-list-mark`, même couleur), d'après la règle de `itemOf` ; un `ListMark`
// qui n'en est pas un pour elle perd sa couleur (`cm-pandoc-text`). Coloration seule :
// l'arbre syntaxique ne contient toujours pas ces listes.
const pandocMark = Decoration.mark({ class: "cm-pandoc-list-mark" });
const pandocText = Decoration.mark({ class: "cm-pandoc-text" });

function pandocMarks(view) {
    const builder = new RangeSetBuilder();
    const { state } = view;
    for (const { from, to } of view.visibleRanges) {
        let line = state.doc.lineAt(from);
        while (true) {
            const item = scanLists(state.doc).get(line.number);
            if (item?.pandoc) {
                const start = line.from + item.indent;
                const end = start + item.text.length;
                if (itemOf(state, line)) builder.add(start, end, pandocMark);
                else if (nodeNames(state, line, item)[0] === "ListMark") builder.add(start, end, pandocText);
            }
            if (line.to >= to || line.number === state.doc.lines) break;
            line = state.doc.line(line.number + 1);
        }
    }
    return builder.finish();
}

export const pandocListMarks = ViewPlugin.fromClass(
    class {
        constructor(view) {
            this.decorations = pandocMarks(view);
        }

        update(update) {
            // L'arbre avance par morceaux : une ligne peut changer de nature sans édition.
            if (update.docChanged || update.viewportChanged || syntaxTree(update.state) !== syntaxTree(update.startState)) {
                this.decorations = pandocMarks(update.view);
            }
        }
    },
    { decorations: (plugin) => plugin.decorations },
);
