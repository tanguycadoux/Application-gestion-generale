// Plan de la note (#314), comme la vue « Plan » de VS Code : les titres du texte, un
// clic ou Entrée pour s'y rendre. Les titres viennent de l'arbre de l'analyseur
// Markdown (pas d'une expression régulière sur le texte) : un `#` dans un bloc de
// code n'en est pas un.
import { ensureSyntaxTree, syntaxTree } from "@codemirror/language";
import { EditorView } from "@codemirror/view";

const HEADING_NODE = /^(?:ATXHeading|SetextHeading)([1-6])$/;
// Retrait par niveau (écrit en entier pour que Tailwind trouve les classes).
const INDENT = ["pl-2", "pl-5", "pl-8", "pl-11", "pl-14", "pl-17"];
const ITEM_CLASSES =
    "block w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-700";
const CURRENT_CLASSES = ["bg-blue-100", "font-semibold"];
const STORAGE_KEY = "note-outline-hidden";

export function readHeadings(state) {
    const tree = ensureSyntaxTree(state, state.doc.length, 100) ?? syntaxTree(state);
    const headings = [];
    tree.iterate({
        enter(node) {
            const match = HEADING_NODE.exec(node.name);
            if (!match) return;
            // Un titre ATX tient sur sa ligne ; un titre souligné (Setext) a son texte
            // sur la première.
            const line = state.doc.lineAt(node.from);
            const text = line.text
                .replace(/^\s{0,3}#{1,6}\s*/, "")
                .replace(/\s+#+\s*$/, "")
                .trim();
            headings.push({ level: Number(match[1]), text: text || "(sans titre)", from: line.from });
            return false;
        },
    });
    return headings;
}

function storedHidden() {
    try {
        const value = localStorage.getItem(STORAGE_KEY);
        if (value !== null) return value === "1";
    } catch {
        // Stockage indisponible : on retombe sur la largeur de la fenêtre.
    }
    // Replié par défaut sur une fenêtre étroite.
    return !window.matchMedia("(min-width: 64rem)").matches;
}

function storeHidden(hidden) {
    try {
        localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
    } catch {
        // Un réglage non gardé n'empêche pas d'écrire.
    }
}

/**
 * Crée le plan. `toggle` est le bouton (cloné d'un <template> du gabarit) qui
 * l'affiche ou le masque, `toolbar` l'endroit où le placer.
 */
export function createOutline(view, { toggleTemplate, toolbar }) {
    const nav = document.createElement("nav");
    nav.id = "note-outline";
    nav.setAttribute("aria-label", "Plan de la note");
    nav.className =
        "flex w-64 shrink-0 flex-col overflow-hidden rounded-lg border border-slate-300 bg-white";

    const title = document.createElement("h2");
    title.textContent = "Plan";
    title.className = "border-b border-slate-300 px-3 py-2 text-sm font-semibold";
    const list = document.createElement("ul");
    list.className = "min-h-0 flex-1 overflow-y-auto p-1";
    const empty = document.createElement("p");
    empty.textContent = "Aucun titre";
    empty.className = "p-3 text-sm text-slate-600";
    nav.append(title, list, empty);

    let headings = [];
    let signature = "";
    let buttons = [];
    let current = -1;

    function currentIndex() {
        const head = view.state.selection.main.head;
        let index = -1;
        headings.forEach((heading, i) => {
            if (heading.from <= head) index = i;
        });
        return index;
    }

    function markCurrent() {
        const index = currentIndex();
        if (index === current) return;
        if (buttons[current]) {
            buttons[current].classList.remove(...CURRENT_CLASSES);
            buttons[current].removeAttribute("aria-current");
        }
        current = index;
        if (!buttons[current]) return;
        buttons[current].classList.add(...CURRENT_CLASSES);
        buttons[current].setAttribute("aria-current", "location");
        // Une seule entrée dans l'ordre de tabulation, comme dans une liste de VS Code ;
        // les flèches font le reste. Le focus de l'utilisateur n'est jamais volé.
        buttons.forEach((button, i) => (button.tabIndex = i === current ? 0 : -1));
        if (!list.contains(document.activeElement))
            buttons[current].scrollIntoView({ block: "nearest" });
    }

    function goTo(index) {
        view.dispatch({
            selection: { anchor: headings[index].from },
            effects: EditorView.scrollIntoView(headings[index].from, { y: "start", yMargin: 8 }),
        });
        view.focus();
    }

    function rebuild() {
        const minLevel = Math.min(...headings.map((heading) => heading.level));
        buttons = headings.map((heading, i) => {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = heading.text;
            // Titre trop long : coupé par une ellipse, lisible en entier au survol.
            button.title = heading.text;
            button.className = `${ITEM_CLASSES} ${INDENT[heading.level - minLevel]}`;
            button.tabIndex = -1;
            button.addEventListener("click", () => goTo(i));
            item.append(button);
            return button;
        });
        list.replaceChildren(...buttons.map((button) => button.parentElement));
        empty.hidden = headings.length > 0;
        current = -1;
        if (buttons.length) buttons[0].tabIndex = 0;
    }

    function refresh() {
        headings = readHeadings(view.state);
        // Reconstruit seulement si les titres ont changé ; sinon les positions seules.
        const next = headings.map((h) => `${h.level}${h.text}`).join("\n");
        if (next !== signature) {
            signature = next;
            rebuild();
        }
        markCurrent();
    }

    list.addEventListener("keydown", (event) => {
        const index = buttons.indexOf(document.activeElement);
        const target = {
            ArrowDown: index + 1,
            ArrowUp: index - 1,
            Home: 0,
            End: buttons.length - 1,
        }[event.key];
        if (index < 0 || target === undefined || !buttons[target]) return;
        event.preventDefault();
        buttons[target].focus();
    });

    const toggle = toggleTemplate.content.firstElementChild.cloneNode(true);
    toggle.classList.add("ml-auto");
    toggle.setAttribute("aria-controls", nav.id);
    function setHidden(hidden) {
        nav.hidden = hidden;
        toggle.setAttribute("aria-expanded", String(!hidden));
    }
    toggle.addEventListener("click", () => {
        setHidden(!nav.hidden);
        storeHidden(nav.hidden);
    });
    toolbar.append(toggle);
    setHidden(storedHidden());
    refresh();

    return {
        element: nav,
        update(update) {
            if (update.docChanged) refresh();
            else if (update.selectionSet) markCurrent();
        },
    };
}
