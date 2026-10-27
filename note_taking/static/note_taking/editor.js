// Éditeur des notes (#89) : CodeMirror 6 à la place du <textarea> du formulaire.
// Les modules sont ceux de static/vendor/codemirror/, résolus par l'import map de la
// page (aucun CDN). Le <textarea> reste dans la page, caché : c'est lui que le
// formulaire envoie, et il reste l'éditeur si ce script ne se charge pas.
import { EditorSelection, EditorState } from "@codemirror/state";
import { EditorView, drawSelection, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import {
    HighlightStyle,
    Language,
    defineLanguageFacet,
    syntaxHighlighting,
} from "@codemirror/language";
import { search, searchKeymap } from "@codemirror/search";
import { tags } from "@lezer/highlight";
import { Strikethrough, TaskList, parser } from "@lezer/markdown";
import { imageFiles, uploadCapture } from "./capture.js";
import { createOutline } from "./outline.js";
import { suggestions } from "./suggestions.js";

// Sans @codemirror/lang-markdown, qui fait charger l'analyseur HTML : seul l'analyseur
// Markdown est embarqué. Les cases `- [ ]` et le barré `~~x~~` sont ceux de Pandoc.
const markdown = new Language(
    defineLanguageFacet(),
    parser.configure([TaskList, Strikethrough]),
    [],
    "markdown",
);

// Couleurs du thème Tailwind (variables de la feuille compilée).
const highlighting = HighlightStyle.define([
    { tag: tags.heading, fontWeight: "bold", color: "var(--color-blue-900)" },
    { tag: tags.strong, fontWeight: "bold" },
    { tag: tags.emphasis, fontStyle: "italic" },
    { tag: tags.strikethrough, textDecoration: "line-through" },
    { tag: tags.link, color: "var(--color-blue-700)" },
    { tag: tags.url, color: "var(--color-blue-700)" },
    { tag: tags.monospace, color: "var(--color-slate-700)" },
    { tag: tags.quote, color: "var(--color-slate-600)", fontStyle: "italic" },
    { tag: tags.comment, color: "var(--color-slate-500)" },
    { tag: tags.labelName, color: "var(--color-slate-600)" },
    // Marqueurs : #, -, *, >, crochets et backticks.
    { tag: tags.processingInstruction, color: "var(--color-amber-700)" },
    { tag: tags.contentSeparator, color: "var(--color-amber-700)" },
]);

const theme = EditorView.theme({
    // Remplit son conteneur et défile en interne ; la mise au point est dessinée par
    // le conteneur (focus-within), CodeMirror réécrivant lui-même la classe de son
    // élément racine.
    "&": { flex: "1 1 0", minHeight: "0" },
    "&.cm-focused": { outline: "none" },
    ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.5" },
    ".cm-content": { padding: "0.25rem 0.5rem" },
});

// Textes du panneau de recherche (Ctrl+F), en anglais par défaut.
const phrases = {
    Find: "Rechercher",
    Replace: "Remplacer",
    next: "suivant",
    previous: "précédent",
    all: "toutes",
    "match case": "respecter la casse",
    "by word": "mot entier",
    regexp: "expression régulière",
    replace: "remplacer",
    "replace all": "tout remplacer",
    close: "fermer",
    "Go to line": "Aller à la ligne",
    go: "aller",
    "current match": "occurrence actuelle",
    "on line": "à la ligne",
    "replaced $ matches": "$ occurrences remplacées",
    "replaced match on line $": "occurrence remplacée à la ligne $",
    "Control character": "Caractère de contrôle",
};

// Images collées ou déposées (#196) : importées, puis `![](images/nom)` à la position du
// curseur (la légende se complète ensuite). Le texte collé n'est pas concerné.
async function insertCaptures(view, files, form) {
    const url = form.dataset.captureUrl;
    const csrf = form.elements.csrfmiddlewaretoken?.value ?? "";
    let separator = "";
    for (const file of files) {
        try {
            const image = await uploadCapture(url, file, csrf);
            const text = `${separator}![](${image.reference})`;
            const { from, to } = view.state.selection.main;
            view.dispatch({
                changes: { from, to, insert: text },
                // Après l'image : une autre capture, ou la suite du texte, vient à la suite.
                selection: EditorSelection.cursor(from + text.length),
                scrollIntoView: true,
                userEvent: "input.paste",
            });
            separator = "\n\n";
            window.Alert?.toast(`L'image « ${image.name} » est importée.`, { type: "success" });
        } catch (error) {
            window.Alert?.toast(error.message, { type: "error" });
        }
    }
    view.focus();
}

function mountEditor(textarea) {
    const label = document.querySelector(`label[for="${textarea.id}"]`);
    const invalid = textarea.getAttribute("aria-invalid") === "true";
    const attributes = {
        "aria-label": label ? label.textContent.trim() : "Contenu de la note",
        spellcheck: "true",
        autocapitalize: "sentences",
    };
    if (invalid) attributes["aria-invalid"] = "true";
    // Raccourcis de l'éditeur (suggestions, recherche) : affichés, et lus avec le champ.
    const help = document.getElementById("editor-help");
    if (help) {
        help.hidden = false;
        attributes["aria-describedby"] = help.id;
    }

    // Adresses des listes de suggestions (#90), sur le formulaire.
    const { projectsUrl, sectionsUrl, imagesUrl } = textarea.form.dataset;
    const suggest = projectsUrl && sectionsUrl && imagesUrl
        ? suggestions({ projects: projectsUrl, sections: sectionsUrl, images: imagesUrl })
        : [];
    let outline;
    const view = new EditorView({
        state: EditorState.create({
            doc: textarea.value,
            extensions: [
                history(),
                drawSelection(),
                markdown.extension,
                suggest,
                syntaxHighlighting(highlighting),
                EditorView.lineWrapping,
                search({ top: true }),
                keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
                EditorState.phrases.of(phrases),
                EditorView.contentAttributes.of(attributes),
                EditorView.domEventHandlers({
                    paste(event, editorView) {
                        const files = imageFiles(event.clipboardData);
                        if (!files.length || !textarea.form.dataset.captureUrl) return false;
                        event.preventDefault();
                        insertCaptures(editorView, files, textarea.form);
                        return true;
                    },
                    drop(event, editorView) {
                        const files = imageFiles(event.dataTransfer);
                        if (!files.length || !textarea.form.dataset.captureUrl) return false;
                        event.preventDefault();
                        // Le curseur se place où l'image est déposée.
                        const position = editorView.posAtCoords({ x: event.clientX, y: event.clientY });
                        if (position !== null) editorView.dispatch({ selection: { anchor: position } });
                        insertCaptures(editorView, files, textarea.form);
                        return true;
                    },
                }),
                theme,
                EditorView.updateListener.of((update) => {
                    if (update.docChanged) textarea.value = update.state.doc.toString();
                    outline?.update(update);
                }),
            ],
        }),
    });

    // Conteneur à nous, aux bordures des champs de formulaire (assets/css/source.css) :
    // il prend la place restante du formulaire, l'éditeur défile dedans.
    const frame = document.createElement("div");
    frame.className = [
        "flex",
        "min-w-0",
        "flex-1",
        "flex-col",
        "overflow-hidden",
        "rounded-lg",
        "border",
        invalid ? "border-red-800" : "border-slate-300",
        "bg-white",
        "focus-within:outline-2",
        "focus-within:outline-offset-2",
        "focus-within:outline-blue-700",
    ].join(" ");
    frame.append(view.dom);

    // L'éditeur et, à côté, le plan de la note (#314) ; le bouton qui l'affiche est
    // cloné du gabarit dans l'en-tête du formulaire.
    const workspace = document.createElement("div");
    workspace.className = "flex min-h-48 min-w-0 flex-1 gap-3";
    const toolbar = textarea.form.querySelector("[data-editor-toolbar]");
    const toggleTemplate = document.getElementById("outline-toggle");
    if (toolbar && toggleTemplate) {
        outline = createOutline(view, { toggleTemplate, toolbar });
        workspace.append(frame, outline.element);
    } else {
        workspace.append(frame);
    }
    textarea.after(workspace);
    textarea.hidden = true;
    return view;
}

const textarea = document.getElementById("body");
if (textarea instanceof HTMLTextAreaElement) mountEditor(textarea);
