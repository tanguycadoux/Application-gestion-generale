// Blocs du menu « Insérer » de l'éditeur (#420), tels que le rendu les lit
// (`note_taking/rendering/`) : insérés sans connaître leur syntaxe.
//
// **Une seule liste**, `blockTemplates` : un nouveau bloc du rendu y prend une ligne. Une
// entrée a `label`, et `blocks` (un sous-menu) ou `skeleton`, le texte à insérer :
// - `«…»` : ce qui est sélectionné une fois inséré, ou le curseur s'il n'y a rien entre ;
// - `wrap` : le squelette d'une sélection, dont le texte remplace `¦` ; sans lui, la
//   sélection n'est pas touchée ;
// - `inline` : dans la ligne, et non sur ses propres lignes ;
// - `fields` : les nombres demandés avant d'insérer ; `skeleton` les reçoit.
import { startCompletion } from "@codemirror/autocomplete";
import { isolateHistory } from "@codemirror/commands";
import { EditorSelection } from "@codemirror/state";
import { tableAt, tableSkeleton } from "./tables.js";

// Le rendu ne va pas plus loin (`LAYOUT_GRID_CLASSES`).
const MAX_LAYOUT = 6;
const CALLOUT = { label: "Callout", skeleton: "::: {.callout-TYPE}\n## «Titre (optionnel)»\n\n:::", wrap: "::: {.callout-TYPE}\n## «Titre (optionnel)»\n\n¦\n:::" };

// Le début d'une ligne dont tout le texte est sélectionné : retrait, puce, numéro, dièses.
const LINE_MARK = /^\s*(?:(?:[-*+>]|#{1,6}|(?:\d+|[A-Za-z]|#)[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)?$/;
const BLANK_LINE = /\n\s*\n/;
// Un renvoi ne se lit pas collé à un mot (`REFERENCE_REGEX`).
const GLUED_BEFORE = /[\p{L}\p{N}_@.]$/u;
const GLUED_AFTER = /^[\p{L}\p{N}_-]/u;

function tableBlock(columns, rows) {
    const { text, cursor } = tableSkeleton(columns, rows);
    return `${text.slice(0, cursor)}«»${text.slice(cursor)}`;
}

function columnsBlock(count) {
    // Sans `width`, les colonnes se partagent la place.
    const columns = Array.from(
        { length: count },
        (_, index) => `::: {.column}\n${index ? "" : "«»"}\n:::`,
    );
    return `::: {.columns}\n${columns.join("\n")}\n:::`;
}

function figureBlock(count) {
    const images = Array.from({ length: count }, (_, index) => `![](images/${index ? "" : "«»"})`);
    return `::: {#fig-nom layout-ncol=${count}}\n${images.join("\n\n")}\n\nLégende\n:::`;
}

/** Les blocs à insérer ; `callouts` : type, libellé et icône de chaque sorte (du serveur). */
function blockTemplates(callouts) {
    return [
        { label: "Tableau…", skeleton: tableBlock, fields: [
            { name: "columns", label: "Colonnes", value: 3, min: 1, max: 20 },
            { name: "rows", label: "Lignes", value: 2, min: 1, max: 50 },
        ] },
        { label: CALLOUT.label, blocks: callouts.map(({ type, label, icon }) => ({
            label,
            icon,
            skeleton: CALLOUT.skeleton.replace("TYPE", type),
            wrap: CALLOUT.wrap.replace("TYPE", type),
        })) },
        { label: "Formule", blocks: [
            { label: "En bloc", skeleton: "$$\n«»\n$$", wrap: "$$\n«¦»\n$$", math: true },
            { label: "Dans la ligne", skeleton: "$«»$", wrap: "$«¦»$", inline: true, math: true },
        ] },
        { label: "Mise en page", blocks: [
            { label: "Colonnes…", skeleton: columnsBlock, fields: [{ name: "columns", label: "Colonnes", value: 2, min: 2, max: MAX_LAYOUT }] },
            { label: "Figure en colonnes…", skeleton: figureBlock, complete: true, fields: [{ name: "images", label: "Images", value: 2, min: 1, max: MAX_LAYOUT }] },
        ] },
        { label: "Métadonnées", skeleton: "::: {.metadata}\ntags: [«»]\n:::" },
        { label: "Légende de tableau", skeleton: ": «Légende» {#tbl-nom}" },
        { label: "Renvoi", blocks: [
            { label: "Vers une figure", skeleton: "@fig-«nom»", inline: true, word: true },
            { label: "Vers un tableau", skeleton: "@tbl-«nom»", inline: true, word: true },
        ] },
    ];
}

/** Le texte d'un squelette et la sélection à y faire ; `selected` remplace `¦`. */
function fill(skeleton, selected) {
    // Découpé avant d'y mettre le texte de la note, où « » et ¦ ne veulent rien dire.
    const [before, inside, after] = skeleton
        .split(/[«»]/)
        .map((part) => part.split("¦").join(selected));
    return {
        text: before + inside + after,
        from: before.length,
        to: before.length + inside.length,
    };
}

/** La partie de la sélection à envelopper, `null` si rien n'est sélectionné. */
function wrappedRange(state, block) {
    let { from, to } = state.selection.main;
    const text = state.sliceDoc(from, to);
    if (!block.wrap || !text.trim()) return null;
    from += text.length - text.trimStart().length;
    to -= text.length - text.trimEnd().length;
    if (block.math) return { from, to };
    const first = state.doc.lineAt(from);
    const last = state.doc.lineAt(to);
    // Un callout prend des lignes entières, sauf un morceau d'une seule ligne.
    if (first.number !== last.number) return { from: first.from, to: last.to };
    return LINE_MARK.test(state.sliceDoc(first.from, from)) ? { from: first.from, to } : { from, to };
}

/** Où insérer un bloc sans sélection : après la ligne du curseur, ou après son tableau. */
function blockPosition(state) {
    const { head } = state.selection.main;
    const line = state.doc.lineAt(head);
    const table = tableAt(state, head);
    if (!table) return line.to;
    let last = state.doc.lineAt(table.to);
    // L'analyseur prend un `:::` collé au tableau pour une de ses lignes.
    while (last.text.trim().startsWith(":::")) last = state.doc.line(last.number - 1);
    return Math.max(line.to, last.to);
}

/** Ce qui sépare un bloc mis en `from`-`to` du texte qui l'entoure : des lignes vides. */
function separate(state, from, to) {
    const { doc } = state;
    const first = doc.lineAt(from);
    const last = doc.lineAt(to);
    const blank = (number) => !doc.line(number).text.trim();
    let prefix = "\n\n";
    if (!state.sliceDoc(first.from, from).trim()) {
        from = first.from;
        prefix = first.number === 1 || blank(first.number - 1) ? "" : "\n";
    } else if (to > from) {
        while (/[ \t]/.test(state.sliceDoc(from - 1, from))) from--;
    }
    let suffix = "\n\n";
    if (!state.sliceDoc(to, last.to).trim()) {
        to = last.to;
        // À la fin de la note, une ligne pour écrire la suite.
        suffix = last.number === doc.lines || !blank(last.number + 1) ? "\n" : "";
    } else {
        while (/[ \t]/.test(state.sliceDoc(to, to + 1))) to++;
    }
    return { from, to, prefix, suffix };
}

/** Insère un bloc, ou en enveloppe la sélection ; un Ctrl+Z l'annule en une fois. */
function insertTemplate(view, block, counts) {
    const { state } = view;
    const wrapped = wrappedRange(state, block);
    let selected = wrapped ? state.sliceDoc(wrapped.from, wrapped.to) : "";
    // Une ligne vide couperait la formule.
    if (block.math) selected = selected.replace(/\n(?:[ \t]*\n)+/g, "\n");
    const skeleton = block.fields ? block.skeleton(...counts) : wrapped ? block.wrap : block.skeleton;
    const { text, ...cursor } = fill(skeleton, selected);
    let place;
    if (block.inline) {
        const { from, to } = wrapped ?? { from: state.selection.main.to, to: state.selection.main.to };
        const line = state.doc.lineAt(from);
        place = {
            from,
            to,
            prefix: block.word && GLUED_BEFORE.test(state.sliceDoc(line.from, from)) ? " " : "",
            suffix: block.word && GLUED_AFTER.test(state.sliceDoc(to, line.to)) ? " " : "",
        };
    } else {
        const at = blockPosition(state);
        place = wrapped ? separate(state, wrapped.from, wrapped.to) : separate(state, at, at);
    }
    const start = place.from + place.prefix.length;
    view.dispatch({
        changes: { from: place.from, to: place.to, insert: place.prefix + text + place.suffix },
        selection: EditorSelection.range(start + cursor.from, start + cursor.to),
        scrollIntoView: true,
        userEvent: "input",
        annotations: isolateHistory.of("full"),
    });
    if (block.complete) startCompletion(view);
}

/** Le choix des nombres d'un bloc (`fields`) ; `close` ferme le menu. */
function countsForm(block) {
    return (view, close) => {
        const form = document.createElement("form");
        form.className = "grid grid-cols-[auto_4rem] items-center gap-2 px-3 py-2";
        form.setAttribute("aria-label", `Insérer : ${block.label.replace("…", "")}`);
        const inputs = block.fields.map(({ name, label, value, min, max }) => {
            const id = `editor-menu-${name}`;
            const caption = document.createElement("label");
            caption.htmlFor = id;
            caption.textContent = label;
            const input = document.createElement("input");
            Object.assign(input, { id, name, type: "number", min: String(min), max: String(max), value: String(value), required: true });
            input.className = "w-16";
            form.append(caption, input);
            return input;
        });
        const submit = document.createElement("button");
        submit.type = "submit";
        submit.className = "col-span-2 rounded-md bg-slate-700 px-3 py-1 text-white";
        submit.textContent = "Insérer";
        form.append(submit);
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const counts = block.fields.map(({ min, max }, index) =>
                Math.min(max, Math.max(min, Number.parseInt(inputs[index].value, 10) || min)),
            );
            close();
            insertTemplate(view, block, counts);
        });
        return form;
    };
}

/** Les sortes de callout, que le gabarit de la page décrit (`{% callout_templates %}`). */
function readCallouts() {
    return [...document.querySelectorAll("template[data-callout]")].map((template) => ({
        type: template.dataset.callout,
        label: template.dataset.label,
        icon: template,
    }));
}

/** Les entrées du menu (`entries`, `editor_menu.js`) ; `showForm` y affiche un formulaire. */
export function blockEntries(view, showForm, blocks = blockTemplates(readCallouts())) {
    const { from, to } = view.state.selection.main;
    const selected = view.state.sliceDoc(from, to).trim();
    return blocks.map((block) => {
        const { label, icon } = block;
        if (block.blocks) return { label, submenu: blockEntries(view, showForm, block.blocks) };
        if (block.fields) return { label, keepOpen: true, run: () => showForm(countsForm(block)) };
        // Une formule dans la ligne ne passe pas d'un paragraphe à l'autre.
        const enabled = !(block.inline && block.wrap && BLANK_LINE.test(selected));
        return { label, icon, enabled, run: () => insertTemplate(view, block) };
    });
}
