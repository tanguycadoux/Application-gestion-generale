// Édition d'un tableau dans une fenêtre à part (#436), sans retour à la ligne : un `<dialog>`
// modal, cloné du gabarit (`#table-dialog-template`), avec un second éditeur.
//
// - Le texte édité est le tableau, sa légende et ses attributs compris (`tableBlocks`), sans
//   le retrait qu'il a dans une liste : seul, l'analyseur y verrait du code.
// - À la validation, il remplace ces lignes en une seule modification. Si elles ne sont plus
//   dans la note (une image importée s'y est insérée, par exemple), rien n'est remplacé.
// - Échap et « Annuler » ferment, après confirmation si le texte a changé. Le clavier est
//   écouté sur le document : le focus peut être sur la page (clic à côté d'un champ).
// - Un élément de la page est inerte, et dessous : les toasts viennent dans la fenêtre, et le
//   menu du clic droit s'y ajoute (`editor_menu.js`).
import { isolateHistory } from "@codemirror/commands";
import { EditorSelection } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { findTables, formatTables } from "./tables.js";

// `: Légende`, et non le `:::` d'un bloc (`TABLE_CAPTION_REGEX`, `rendering/tables.py`).
const CAPTION = /^\s*(?:[Tt]able)?:(?!::)/;
// Ce qui borne un paragraphe, donc une légende : une ligne vide, un bloc, un titre, un tableau.
const BOUNDARY = /^\s*(?:$|:::|#{1,6}\s|\|)/;

const indentOf = (text) => /^\s*/.exec(text)[0];

/** La première ligne de la légende au-dessus de la ligne `number`, `number` sans légende. */
function captionAbove(doc, number, floor) {
    const indent = indentOf(doc.line(number).text);
    let current = number - 1;
    while (current > floor && !doc.line(current).text.trim()) current--;
    for (; current > floor && !BOUNDARY.test(doc.line(current).text); current--) {
        // Une légende est un paragraphe entier : la ligne qui le commence.
        const starts = current - 1 === floor || BOUNDARY.test(doc.line(current - 1).text);
        if (starts) {
            const { text } = doc.line(current);
            return CAPTION.test(text) && indentOf(text) === indent ? current : number;
        }
    }
    return number;
}

/** La dernière ligne de la légende sous la ligne `number`, `number` sans légende. */
function captionBelow(doc, number, indent) {
    let current = number + 1;
    while (current <= doc.lines && !doc.line(current).text.trim()) current++;
    if (current > doc.lines) return number;
    const { text } = doc.line(current);
    if (!CAPTION.test(text) || indentOf(text) !== indent) return number;
    while (current < doc.lines && !BOUNDARY.test(doc.line(current + 1).text)) current++;
    return current;
}

/**
 * Les tableaux à barres de la note, légende comprise : `{ from, to }`. Comme dans le rendu,
 * la légende d'avant l'emporte, et celle d'un tableau n'est plus à prendre pour le suivant.
 */
function tableBlocks(state) {
    const { doc } = state;
    let floor = 0;
    return findTables(state).map(({ from, to }) => {
        const header = doc.lineAt(from);
        let first = header.number;
        let last = doc.lineAt(to).number;
        first = captionAbove(doc, first, floor);
        if (first === header.number) last = captionBelow(doc, last, indentOf(header.text));
        floor = last;
        return { from: doc.line(first).from, to: doc.line(last).to };
    });
}

/** Le tableau et sa légende à la position `pos` : `{ from, to }`, sinon `null`. */
export function tableBlockAt(state, pos) {
    return tableBlocks(state).find(({ from, to }) => from <= pos && pos <= to) ?? null;
}

function dedent(text, indent) {
    return text
        .split("\n")
        .map((line) => line.slice(Math.min(indent.length, indentOf(line).length)))
        .join("\n");
}

function reindent(text, indent) {
    return text
        .split("\n")
        .map((line) => (line.trim() ? indent + line : line))
        .join("\n");
}

/**
 * Ouvre le tableau à la position `pos` de l'éditeur de la note. `createEditor(doc, extensions)`
 * crée l'éditeur de la fenêtre, semblable à celui de la note (`editor.js`).
 */
export function openTableDialog(noteView, pos, createEditor) {
    const block = tableBlockAt(noteView.state, pos);
    const template = document.getElementById("table-dialog-template");
    if (!block || !template) return;

    const original = noteView.state.sliceDoc(block.from, block.to);
    const indent = indentOf(original);
    const initial = dedent(original, indent);
    const dialog = template.content.firstElementChild.cloneNode(true);
    const [format, cancel, validate, discard] = ["format", "cancel", "validate", "discard"].map(
        (name) => dialog.querySelector(`button[name="${name}"]`),
    );
    const confirmation = dialog.querySelector("[popover]");
    const message = dialog.querySelector("[data-table-message]");
    const toasts = document.getElementById("toasts");

    const tableView = createEditor(initial, [
        EditorView.contentAttributes.of({
            "aria-label": "Tableau",
            "aria-describedby": "table-dialog-help",
            spellcheck: "true",
            autocapitalize: "sentences",
        }),
        EditorView.updateListener.of((update) => {
            if (update.docChanged) showMessage("");
        }),
    ]);
    dialog.querySelector("[data-table-editor]").append(tableView.dom);

    const text = () => tableView.state.doc.toString();
    const changed = () => text() !== initial;

    function showMessage(content) {
        message.textContent = content;
        message.hidden = !content;
    }

    function formatText() {
        const tables = findTables(tableView.state);
        formatTables(tableView, tables);
        // Les colonnes alignées se lisent depuis la première.
        tableView.scrollDOM.scrollLeft = 0;
        tableView.focus();
        if (!tables.length) {
            showMessage("Rien à formater : il manque la ligne de séparation (|---|---|) sous l'en-tête.");
        }
    }

    function validateText() {
        if (!changed()) {
            dialog.close();
            return;
        }
        const { state } = noteView;
        // Les mêmes lignes, même si du texte ajouté plus haut les a décalées.
        const same = tableBlocks(state).filter(({ from, to }) => state.sliceDoc(from, to) === original);
        const target = same.find(({ from }) => from === block.from) ?? (same.length === 1 ? same[0] : null);
        if (!target) {
            showMessage("Le tableau a changé dans la note depuis l'ouverture de cette fenêtre : rien n'y est remplacé. Copiez votre texte, annulez, puis reportez-le dans la note.");
            tableView.focus();
            return;
        }
        const recognized = findTables(tableView.state).length > 0;
        const before = tableView.state.sliceDoc(0, tableView.state.selection.main.head);
        noteView.dispatch({
            changes: { from: target.from, to: target.to, insert: reindent(text(), indent) },
            selection: EditorSelection.cursor(target.from + reindent(before, indent).length),
            scrollIntoView: true,
            userEvent: "input.table",
            annotations: isolateHistory.of("full"),
        });
        dialog.close();
        if (!recognized) {
            window.Toast?.show("Le texte validé n'est plus un tableau : il manque la ligne de séparation (|---|---|) sous l'en-tête. Ctrl+Z revient au tableau d'avant.");
        }
    }

    function escape() {
        if (confirmation.matches(":popover-open")) confirmation.hidePopover();
        else cancel.click();
    }

    const inOtherDialog = (event) => {
        const other = event.target.closest?.("dialog");
        return Boolean(other) && other !== dialog;
    };

    // Avant l'éditeur (Ctrl+Entrée y ajoute une ligne) et la page (Ctrl+S, `note_form.js`).
    function shortcuts(event) {
        if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
        const save = event.key.toLowerCase() === "s";
        const enter = event.key === "Enter" && !inOtherDialog(event) && !event.target.closest?.('[role="menu"]');
        if (!save && !enter) return;
        event.preventDefault();
        event.stopPropagation();
        if (enter) validateText();
        else showMessage("La note n'est pas enregistrée : validez d'abord le tableau (Ctrl+Entrée), puis Ctrl+S.");
    }

    // Après l'éditeur et le menu, qui ont aussi un usage d'Échap. Le navigateur ne ferme pas la
    // fenêtre lui-même : Chrome le ferait sans confirmation à la deuxième fois.
    function keydown(event) {
        if (event.key !== "Escape" || event.isComposing || event.defaultPrevented || inOtherDialog(event)) return;
        event.preventDefault();
        if (!event.target.closest?.("[data-toast]")) escape();
    }

    function beforeUnload(event) {
        if (!changed()) return;
        event.preventDefault();
        event.returnValue = "";
    }

    format.addEventListener("click", formatText);
    validate.addEventListener("click", validateText);
    discard.addEventListener("click", () => dialog.close());
    cancel.addEventListener("click", (event) => {
        // Le bouton ouvre la confirmation, qui n'a pas lieu d'être sans modification.
        if (changed()) return;
        event.preventDefault();
        dialog.close();
    });
    confirmation.addEventListener("toggle", (event) => {
        if (event.newState === "open") confirmation.querySelector("button").focus();
    });
    dialog.addEventListener("cancel", (event) => {
        if (event.target !== dialog) return;
        event.preventDefault();
        escape();
    });
    dialog.addEventListener("close", () => {
        document.removeEventListener("keydown", shortcuts, true);
        document.removeEventListener("keydown", keydown);
        window.removeEventListener("beforeunload", beforeUnload);
        if (toasts) document.body.append(toasts);
        tableView.destroy();
        dialog.remove();
        noteView.focus();
    }, { once: true });
    document.addEventListener("keydown", shortcuts, true);
    document.addEventListener("keydown", keydown);
    window.addEventListener("beforeunload", beforeUnload);

    document.body.append(dialog);
    if (toasts) dialog.append(toasts);
    dialog.showModal();
    const before = noteView.state.sliceDoc(block.from, Math.max(block.from, Math.min(pos, block.to)));
    tableView.dispatch({
        selection: EditorSelection.cursor(Math.min(dedent(before, indent).length, initial.length)),
        scrollIntoView: true,
    });
    tableView.focus();
}
