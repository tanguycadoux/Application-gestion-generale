// Menu du clic droit de l'éditeur (#400, #437) : insérer du contenu sans connaître la syntaxe.
//
// - Clic droit : notre menu, à la place de celui du navigateur ; **Maj + clic droit** garde
//   celui du navigateur (correcteur orthographique), comme le rappelle la dernière ligne.
// - Clavier : Maj+F10 ou la touche Menu l'ouvrent au curseur ; flèches, Début, Fin pour se
//   déplacer, flèche droite ou Entrée pour ouvrir un sous-menu, flèche gauche pour le fermer,
//   Entrée pour choisir, Échap pour tout fermer (le curseur revient dans l'éditeur).
// - **Une seule liste** décrit le menu, `entries` : une issue y ajoute ses entrées sans
//   toucher au reste. Une entrée a `label` et, au choix : `shortcut` (affiché), `when`
//   (absente si faux), `enabled` (grisée si faux), `run` ou `submenu` (une liste). Un
//   `separator` sépare deux groupes.
import { startCompletion } from "@codemirror/autocomplete";
import { EditorSelection } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { findTables, formatTables, tableAt, tableSkeleton } from "./tables.js";

const MAX_COLUMNS = 20;
const MAX_ROWS = 50;
// Le temps d'aller en diagonale de l'entrée à son sous-menu.
const SUBMENU_DELAY = 250;

const PANEL_CLASS =
    "fixed z-50 min-w-56 rounded-lg border border-slate-200 bg-white py-1 text-sm text-black shadow-lg";
const ITEM_CLASS =
    "flex w-full items-baseline gap-6 rounded px-3 py-1 text-left whitespace-nowrap hover:bg-slate-100 focus:bg-slate-100 focus:outline-none aria-expanded:bg-slate-100 disabled:text-slate-400 disabled:hover:bg-transparent";

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

/** Couper ou copier par le navigateur : l'éditeur y met sa sélection, comme Ctrl+X et Ctrl+C. */
function clipboardCommand(view, command, shortcut) {
    view.focus();
    if (!document.execCommand(command)) {
        window.Toast?.show(`Le navigateur refuse l'accès au presse-papiers. Utilisez ${shortcut}.`);
    }
}

/** Colle le presse-papiers : une image par le même chemin qu'une capture (#196), sinon le texte. */
async function paste(view, importImages) {
    let text = "";
    try {
        for (const item of await navigator.clipboard.read()) {
            const type = item.types.find((name) => name.startsWith("image/"));
            if (type && importImages) {
                const extension = type.slice("image/".length).split("+")[0];
                const image = new File([await item.getType(type)], `image.${extension}`, { type });
                view.focus();
                importImages(view, [image]);
                return;
            }
            if (item.types.includes("text/plain")) {
                text += await (await item.getType("text/plain")).text();
            }
        }
    } catch {
        // Refusé, ou page servie sans HTTPS ailleurs que sur cet ordinateur.
        window.Toast?.show("Le navigateur refuse l'accès au presse-papiers. Utilisez Ctrl+V.");
        view.focus();
        return;
    }
    view.focus();
    if (!text) return;
    view.dispatch(view.state.replaceSelection(view.state.toText(text)), {
        scrollIntoView: true,
        userEvent: "input.paste",
    });
}

/** Le libellé du formatage groupé : son nombre de tableaux, de la sélection ou de la note. */
function formatLabel(count, selected) {
    if (!selected) return count ? `Formater tous les tableaux (${count})` : "Formater tous les tableaux";
    if (count === 1) return "Formater le tableau de la sélection";
    return count ? `Formater les ${count} tableaux de la sélection` : "Formater les tableaux de la sélection";
}

/**
 * Le menu, pour un clic à la position `pos`. `importImages` et `images` : voir `editorMenu` ;
 * `showForm` remplace le menu par un formulaire.
 */
function entries(view, pos, { importImages, images, showForm }) {
    const { state } = view;
    const selected = state.selection.ranges.some((range) => !range.empty);
    const table = tableAt(state, pos);
    const here = table ? findTables(state, [{ from: pos, to: pos }]) : [];
    const tables = findTables(
        state,
        selected ? state.selection.ranges.filter((range) => !range.empty) : null,
    );
    return [
        {
            label: "Couper",
            shortcut: "Ctrl+X",
            enabled: selected,
            run: () => clipboardCommand(view, "cut", "Ctrl+X"),
        },
        {
            label: "Copier",
            shortcut: "Ctrl+C",
            enabled: selected,
            run: () => clipboardCommand(view, "copy", "Ctrl+C"),
        },
        { label: "Coller", shortcut: "Ctrl+V", run: () => paste(view, importImages) },
        { separator: true },
        {
            label: "Insérer",
            submenu: [
                { label: "Image existante…", when: images, run: () => insertImage(view) },
                {
                    label: "Importer une image…",
                    when: Boolean(importImages),
                    run: () => chooseImages(view, importImages),
                },
                { label: "Tableau…", keepOpen: true, run: () => showForm(tableForm) },
            ],
        },
        { separator: true },
        {
            label: "Tableau",
            when: Boolean(table),
            submenu: [
                {
                    label: "Formater le tableau",
                    enabled: here.length > 0,
                    run: () => formatTables(view, here),
                },
            ],
        },
        {
            label: formatLabel(tables.length, selected),
            enabled: tables.length > 0,
            run: () => formatTables(view, tables),
        },
    ];
}

/** Écrit `![` et ouvre la liste des images (#92). */
function insertImage(view) {
    const { from, to } = view.state.selection.main;
    view.dispatch({
        changes: { from, to, insert: "![" },
        selection: EditorSelection.cursor(from + 2),
        userEvent: "input",
    });
    startCompletion(view);
}

function chooseImages(view, importImages) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.multiple = true;
    input.addEventListener("change", () => {
        if (input.files.length) importImages(view, [...input.files]);
    });
    input.click();
}

/** Le choix des colonnes et des lignes d'un tableau à insérer ; `close` ferme le menu. */
function tableForm(view, close) {
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
        close();
        insertBlock(view, skeleton.text, skeleton.cursor);
    });
    return form;
}

/** Sans les entrées absentes ni les séparateurs qui ne séparent plus rien. */
function shown(list) {
    const kept = list.filter(
        (entry) => (entry.when ?? true) && (!entry.submenu || shown(entry.submenu).length),
    );
    return kept.filter(
        (entry, index) => !entry.separator || (index > 0 && index < kept.length - 1 && !kept[index + 1].separator),
    );
}

/** Place un panneau dans la fenêtre : il ne dépasse ni à droite ni en bas. */
function place(panel, x, y) {
    const { width, height } = panel.getBoundingClientRect();
    panel.style.left = `${Math.max(0, Math.min(x, window.innerWidth - width - 4))}px`;
    panel.style.top = `${Math.max(0, Math.min(y, window.innerHeight - height - 4))}px`;
}

/** Les entrées actives d'un panneau, sans celles de ses sous-menus. */
function itemsOf(panel) {
    return [...panel.querySelectorAll('[role="menuitem"]:not(:disabled)')].filter(
        (item) => item.closest('[role="menu"]') === panel,
    );
}

function openSubmenu(item, { focus = false } = {}) {
    const submenu = item.nextElementSibling;
    closeSubmenus(item.closest('[role="menu"]'), item);
    submenu.hidden = false;
    item.setAttribute("aria-expanded", "true");
    const box = item.getBoundingClientRect();
    const { width } = submenu.getBoundingClientRect();
    // À droite de l'entrée, ou à gauche s'il n'y a pas la place.
    const right = box.right + width + 4 <= window.innerWidth;
    place(submenu, right ? box.right : box.left - width, box.top - 5);
    if (focus) itemsOf(submenu)[0]?.focus();
}

/** Ferme les sous-menus ouverts d'un panneau, sauf celui de `except`. */
function closeSubmenus(panel, except = null) {
    for (const item of panel.querySelectorAll('[aria-expanded="true"]')) {
        if (item === except) continue;
        item.setAttribute("aria-expanded", "false");
        item.nextElementSibling.hidden = true;
    }
}

/** Un panneau (le menu ou un sous-menu) ; `choose(entry)` exécute une entrée choisie. */
function buildPanel(list, label, choose) {
    const panel = document.createElement("div");
    panel.setAttribute("role", "menu");
    panel.setAttribute("aria-label", label);
    panel.className = PANEL_CLASS;
    // Le sous-menu ouvert se referme quand le pointeur s'attarde sur une autre entrée.
    let timer = 0;
    panel.addEventListener("pointerenter", () => clearTimeout(timer));
    for (const entry of shown(list)) {
        if (entry.separator) {
            const line = document.createElement("div");
            line.setAttribute("role", "separator");
            line.className = "my-1 border-t border-slate-200";
            panel.append(line);
            continue;
        }
        const item = document.createElement("button");
        item.type = "button";
        item.setAttribute("role", "menuitem");
        item.tabIndex = -1;
        item.className = ITEM_CLASS;
        item.disabled = !(entry.enabled ?? true);
        const text = document.createElement("span");
        text.className = "flex-1";
        text.textContent = entry.label;
        item.append(text);
        if (entry.shortcut || entry.submenu) {
            const mark = document.createElement("span");
            mark.className = "text-xs text-slate-600";
            mark.setAttribute("aria-hidden", "true");
            mark.textContent = entry.submenu ? "▸" : entry.shortcut;
            item.append(mark);
        }
        if (entry.shortcut) {
            item.setAttribute("aria-keyshortcuts", entry.shortcut.replace("Ctrl", "Control"));
        }
        item.addEventListener("pointerenter", (event) => {
            if (event.pointerType !== "mouse") return;
            clearTimeout(timer);
            timer = setTimeout(() => {
                if (!item.isConnected) return;
                if (entry.submenu) openSubmenu(item);
                else closeSubmenus(panel);
            }, SUBMENU_DELAY);
        });
        if (!entry.submenu) {
            item.addEventListener("click", () => choose(entry));
            panel.append(item);
            continue;
        }
        item.setAttribute("aria-haspopup", "menu");
        item.setAttribute("aria-expanded", "false");
        // `detail` vaut 0 pour Entrée ou Espace : le sous-menu prend alors le focus.
        item.addEventListener("click", (event) => openSubmenu(item, { focus: event.detail === 0 }));
        const submenu = buildPanel(entry.submenu, entry.label, choose);
        submenu.hidden = true;
        // Aller dans le sous-menu annule la fermeture demandée en chemin.
        submenu.addEventListener("pointerenter", () => clearTimeout(timer));
        const group = document.createElement("div");
        group.setAttribute("role", "none");
        group.append(item, submenu);
        panel.append(group);
    }
    return panel;
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

    function keydown(event, view) {
        const item = event.target.closest('[role="menuitem"]');
        const panel = item?.closest('[role="menu"]');
        const move = (index) => {
            const all = itemsOf(panel);
            closeSubmenus(panel);
            all[(index + all.length) % all.length]?.focus();
        };
        if (event.key === "Escape") {
            event.preventDefault();
            close(view);
        } else if (event.key === "Tab") {
            // Dans le formulaire, Tab va d'un champ à l'autre.
            if (!event.target.closest("form")) close(view, false);
        } else if (!item) {
            // Les champs du formulaire gardent leurs flèches.
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            move(itemsOf(panel).indexOf(item) + 1);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            move(itemsOf(panel).indexOf(item) - 1);
        } else if (event.key === "Home") {
            event.preventDefault();
            move(0);
        } else if (event.key === "End") {
            event.preventDefault();
            move(-1);
        } else if (event.key === "ArrowRight" && item.hasAttribute("aria-haspopup")) {
            event.preventDefault();
            openSubmenu(item, { focus: true });
        } else if (event.key === "ArrowLeft" && panel !== menu) {
            event.preventDefault();
            const parent = panel.previousElementSibling;
            closeSubmenus(parent.closest('[role="menu"]'));
            parent.focus();
        }
    }

    function open(view, x, y, pos) {
        close(view, false);
        const showForm = (build) => {
            const form = build(view, () => close(view));
            menu.replaceChildren(form);
            place(menu, x, y);
            form.querySelector("input")?.select();
        };
        menu = buildPanel(
            entries(view, pos, { importImages, images, showForm }),
            "Menu de l'éditeur",
            (entry) => {
                // Une entrée qui affiche un formulaire garde le menu ouvert.
                if (!entry.keepOpen) close(view);
                entry.run();
            },
        );
        menu.closeMenu = (refocus) => close(view, refocus);
        const hint = document.createElement("p");
        hint.className = "mt-1 border-t border-slate-200 px-3 pt-1 text-xs text-slate-600";
        hint.textContent = "Menu du navigateur : Maj + clic droit";
        menu.append(hint);
        menu.addEventListener("keydown", (event) => keydown(event, view));
        document.body.append(menu);
        place(menu, x, y);
        document.addEventListener("pointerdown", outside, true);
        itemsOf(menu)[0]?.focus();
    }

    function openAtCursor(view) {
        const { head } = view.state.selection.main;
        const coords = view.coordsAtPos(head);
        const box = view.contentDOM.getBoundingClientRect();
        openedByKeyboard = Date.now();
        open(view, coords?.left ?? box.left, coords?.bottom ?? box.top, head);
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
                const { from, to, head } = view.state.selection.main;
                if (position !== null && (position < from || position > to)) {
                    view.dispatch({ selection: { anchor: position } });
                }
                open(view, event.clientX, event.clientY, position ?? head);
                return true;
            },
        }),
    ];
}
