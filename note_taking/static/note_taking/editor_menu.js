// Menu du clic droit de l'éditeur (#400) : insérer du contenu sans connaître la syntaxe.
//
// - Clic droit : notre menu, à la place de celui du navigateur ; **Maj + clic droit** garde
//   celui du navigateur (copier, coller, correcteur orthographique), comme le rappelle la
//   dernière ligne du menu.
// - Clavier : Maj+F10 ou la touche Menu l'ouvrent au curseur ; flèches, Début, Fin pour se
//   déplacer, Entrée pour choisir, Échap pour fermer (le curseur revient dans l'éditeur).
// - Entrées : une image existante (la liste des suggestions d'images, #92), importer une
//   image (même chemin que les captures, #196), un tableau (nombre de colonnes et de
//   lignes), et « Formater le tableau » (#401) quand le curseur est dans un tableau.
import { startCompletion } from "@codemirror/autocomplete";
import { EditorSelection } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { formatTableAtCursor, tableAt, tableSkeleton } from "./tables.js";

const MAX_COLUMNS = 20;
const MAX_ROWS = 50;

const ITEM_CLASS =
    "block w-full rounded px-3 py-1 text-left hover:bg-slate-100 focus:bg-slate-100 focus:outline-none";

/** Insère `text` en bloc au curseur : sur sa propre ligne, séparé du texte par des lignes vides. */
function insertBlock(view, text, cursorOffset) {
    const { state } = view;
    const line = state.doc.lineAt(state.selection.main.head);
    const blank = !line.text.trim();
    const at = blank ? line.from : line.to;
    const previous = line.number > 1 ? state.doc.line(line.number - 1) : null;
    const next = line.number < state.doc.lines ? state.doc.line(line.number + 1) : null;
    let prefix = "";
    if (!blank) prefix = "\n\n";
    else if (previous && previous.text.trim()) prefix = "\n";
    const after = blank ? line : next;
    const suffix = after && (blank ? next?.text.trim() : after.text.trim()) ? "\n" : "";
    const insert = `${prefix}${text}${blank ? "" : "\n"}${suffix}`;
    view.dispatch({
        changes: { from: at, to: at, insert },
        selection: EditorSelection.cursor(at + prefix.length + cursorOffset),
        scrollIntoView: true,
        userEvent: "input",
    });
}

/**
 * L'extension du menu. `importImages(view, files)` importe des fichiers image et insère leur
 * référence ; sans elle, ni `images` (suggestions d'images disponibles), l'entrée
 * correspondante n'apparaît pas.
 */
export function editorMenu({ importImages = null, images = false } = {}) {
    let menu = null;
    let openedByKeyboard = 0;

    function close(view, refocus = true) {
        if (!menu) return;
        menu.remove();
        menu = null;
        document.removeEventListener("pointerdown", outside, true);
        if (refocus) view.focus();
    }

    function outside(event) {
        if (menu && !menu.contains(event.target)) menu.closeMenu(false);
    }

    function items() {
        return [...menu.querySelectorAll('[role="menuitem"]')];
    }

    function move(delta, index = null) {
        const all = items();
        const current = all.indexOf(document.activeElement);
        const target = index ?? (current + delta + all.length) % all.length;
        all[target]?.focus();
    }

    function button(label, run) {
        const item = document.createElement("button");
        item.type = "button";
        item.setAttribute("role", "menuitem");
        item.tabIndex = -1;
        item.className = ITEM_CLASS;
        item.textContent = label;
        item.addEventListener("click", run);
        return item;
    }

    function place(x, y) {
        // Dans la fenêtre : le menu ne dépasse ni à droite ni en bas.
        const { width, height } = menu.getBoundingClientRect();
        menu.style.left = `${Math.max(0, Math.min(x, window.innerWidth - width - 4))}px`;
        menu.style.top = `${Math.max(0, Math.min(y, window.innerHeight - height - 4))}px`;
    }

    function tableForm(view) {
        // Le choix des colonnes et des lignes remplace les entrées, dans le même menu.
        const form = document.createElement("form");
        form.className = "grid grid-cols-[auto_4rem] items-center gap-2 px-3 py-2";
        form.setAttribute("aria-label", "Insérer un tableau");
        const field = (name, label, value, max) => {
            const id = `editor-menu-${name}`;
            const caption = document.createElement("label");
            caption.htmlFor = id;
            caption.textContent = label;
            const input = document.createElement("input");
            Object.assign(input, { id, name, type: "number", min: "1", max: String(max), value: String(value), required: true });
            input.className = "w-16";
            form.append(caption, input);
            return input;
        };
        const columns = field("columns", "Colonnes", 3, MAX_COLUMNS);
        const rows = field("rows", "Lignes", 2, MAX_ROWS);
        const submit = document.createElement("button");
        submit.type = "submit";
        submit.className = "col-span-2 rounded-md bg-slate-700 px-3 py-1 text-white";
        submit.textContent = "Insérer";
        form.append(submit);
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const count = (input, max) => Math.min(max, Math.max(1, Number.parseInt(input.value, 10) || 1));
            const skeleton = tableSkeleton(count(columns, MAX_COLUMNS), count(rows, MAX_ROWS));
            close(view);
            insertBlock(view, skeleton.text, skeleton.cursor);
        });
        menu.replaceChildren(form);
        columns.focus();
        columns.select();
    }

    function open(view, x, y) {
        close(view, false);
        menu = document.createElement("div");
        menu.setAttribute("role", "menu");
        menu.setAttribute("aria-label", "Insérer");
        menu.className =
            "fixed z-50 min-w-56 rounded-lg border border-slate-200 bg-white py-1 text-sm text-black shadow-lg";
        menu.closeMenu = (refocus) => close(view, refocus);

        if (images) {
            menu.append(
                button("Image existante…", () => {
                    close(view);
                    const { from, to } = view.state.selection.main;
                    view.dispatch({
                        changes: { from, to, insert: "![" },
                        selection: EditorSelection.cursor(from + 2),
                        userEvent: "input",
                    });
                    startCompletion(view);
                }),
            );
        }
        if (importImages) {
            menu.append(
                button("Importer une image…", () => {
                    close(view);
                    const input = document.createElement("input");
                    input.type = "file";
                    input.accept = "image/*";
                    input.multiple = true;
                    input.addEventListener("change", () => {
                        if (input.files.length) importImages(view, [...input.files]);
                    });
                    input.click();
                }),
            );
        }
        menu.append(button("Tableau…", () => tableForm(view)));
        if (tableAt(view.state, view.state.selection.main.head)) {
            menu.append(
                button("Formater le tableau", () => {
                    close(view);
                    formatTableAtCursor(view);
                }),
            );
        }
        const hint = document.createElement("p");
        hint.className = "mt-1 border-t border-slate-200 px-3 pt-1 text-xs text-slate-600";
        hint.textContent = "Menu du navigateur : Maj + clic droit";
        menu.append(hint);

        menu.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                close(view);
            } else if (event.key === "Tab") {
                close(view, false);
            } else if (event.target.closest("form")) {
                // Les champs du tableau gardent leurs flèches.
            } else if (event.key === "ArrowDown") {
                event.preventDefault();
                move(1);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                move(-1);
            } else if (event.key === "Home") {
                event.preventDefault();
                move(0, 0);
            } else if (event.key === "End") {
                event.preventDefault();
                move(0, items().length - 1);
            }
        });
        document.body.append(menu);
        place(x, y);
        document.addEventListener("pointerdown", outside, true);
        items()[0]?.focus();
    }

    function openAtCursor(view) {
        const coords = view.coordsAtPos(view.state.selection.main.head);
        const box = view.contentDOM.getBoundingClientRect();
        openedByKeyboard = Date.now();
        open(view, coords?.left ?? box.left, coords?.bottom ?? box.top);
        return true;
    }

    return [
        keymap.of([
            { key: "Shift-F10", run: openAtCursor },
            { key: "ContextMenu", run: openAtCursor },
        ]),
        EditorView.domEventHandlers({
            contextmenu(event, view) {
                if (event.shiftKey) return false;
                event.preventDefault();
                // Le menu ouvert au clavier : le navigateur envoie aussi l'événement.
                if (Date.now() - openedByKeyboard < 500) return true;
                // Le curseur vient au clic, sauf dans la sélection (la garder).
                const position = view.posAtCoords({ x: event.clientX, y: event.clientY });
                const { from, to } = view.state.selection.main;
                if (position !== null && (position < from || position > to)) {
                    view.dispatch({ selection: { anchor: position } });
                }
                open(view, event.clientX, event.clientY);
                return true;
            },
        }),
    ];
}
