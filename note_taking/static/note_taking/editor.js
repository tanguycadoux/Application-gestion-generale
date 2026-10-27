// Éditeur des notes (#89) : CodeMirror 6 à la place du <textarea> du formulaire.
// Les modules sont ceux de static/vendor/codemirror/, résolus par l'import map de la
// page (aucun CDN). Le <textarea> reste dans la page, caché : c'est lui que le
// formulaire envoie, et il reste l'éditeur si ce script ne se charge pas.
import { EditorState } from "@codemirror/state";
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
    "&.cm-focused": {
        outline: "2px solid var(--color-blue-700)",
        outlineOffset: "2px",
    },
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

function mountEditor(textarea) {
    const label = document.querySelector(`label[for="${textarea.id}"]`);
    const invalid = textarea.getAttribute("aria-invalid") === "true";
    const attributes = {
        "aria-label": label ? label.textContent.trim() : "Contenu de la note",
        spellcheck: "true",
        autocapitalize: "sentences",
    };
    if (invalid) attributes["aria-invalid"] = "true";

    const view = new EditorView({
        state: EditorState.create({
            doc: textarea.value,
            extensions: [
                history(),
                drawSelection(),
                markdown.extension,
                syntaxHighlighting(highlighting),
                EditorView.lineWrapping,
                search({ top: true }),
                keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
                EditorState.phrases.of(phrases),
                EditorView.contentAttributes.of(attributes),
                theme,
                EditorView.updateListener.of((update) => {
                    if (update.docChanged) textarea.value = update.state.doc.toString();
                }),
            ],
        }),
    });

    // Mêmes bordures que les champs de formulaire (assets/css/source.css), et la
    // même hauteur que l'ancien <textarea>, ajustable à la souris.
    view.dom.classList.add(
        "col-span-2",
        "h-96",
        "min-w-0",
        "resize-y",
        "overflow-hidden",
        "rounded-lg",
        "border",
        invalid ? "border-red-800" : "border-slate-300",
        "bg-white",
    );
    textarea.after(view.dom);
    textarea.hidden = true;
    return view;
}

const textarea = document.getElementById("body");
if (textarea instanceof HTMLTextAreaElement) mountEditor(textarea);
