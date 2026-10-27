// Suggestions de l'éditeur (#91, #92) : en tapant, l'éditeur propose ce qui existe.
//   `# `        -> les projets ;
//   `## ` ...   -> les niveaux du chemin, sous le projet et les titres déjà écrits ;
//   `![`        -> les images, avec leur vignette (insère `![](images/nom)`).
// Les listes viennent des vues JSON de #90 (adresses sur le formulaire) ; rien n'est
// créé ici : un nom nouveau se tape tel quel et se crée à l'enregistrement.
import {
    acceptCompletion,
    autocompletion,
    completionStatus,
    moveCompletionSelection,
    selectedCompletion,
} from "@codemirror/autocomplete";
import { EditorSelection, EditorState, Prec } from "@codemirror/state";
import { keymap } from "@codemirror/view";
import { readHeadings } from "./outline.js";

const IMAGE_TRIGGER = /!\[([^\]\n]*)$/;
// Une image dont la référence est en cours d'écriture : ![légende](images/ba
const IMAGE_PATH_TRIGGER = /!\[[^\]\n]*\]\(images\/([^)\s]*)$/;

const phrases = { Completions: "Suggestions" };

async function fetchResults(url, params, context) {
    const controller = new AbortController();
    context.addEventListener("abort", () => controller.abort());
    const query = new URLSearchParams(params);
    try {
        const response = await fetch(`${url}?${query}`, {
            signal: controller.signal,
            headers: { Accept: "application/json" },
        });
        if (!response.ok) return null;
        return (await response.json()).results;
    } catch {
        // Requête annulée (la saisie a changé) ou serveur injoignable : pas de liste.
        return null;
    }
}

// « / » sépare les niveaux d'un chemin saisi, « // » en est un littéral (core/sections.py).
const joinPath = (levels) => levels.map((name) => name.replaceAll("/", "//")).join("/");

/**
 * Le projet et les niveaux au-dessus d'un titre de niveau `level` : la suite des titres
 * parents, dans l'ordre. `null` si un niveau manque (titre qui saute un niveau), ou si
 * aucun projet (`#`) n'est écrit plus haut.
 */
export function pathAbove(headings, line, level) {
    const stack = [];
    for (const heading of headings) {
        if (heading.from >= line.from) break;
        stack[heading.level] = heading.text;
        stack.length = heading.level + 1;
    }
    const levels = [];
    for (let i = 1; i < level; i++) {
        if (stack[i] === undefined) return null;
        levels.push(stack[i]);
    }
    return levels.length ? { project: levels[0], path: levels.slice(1) } : null;
}

function titleSource(urls) {
    return async (context) => {
        const line = context.state.doc.lineAt(context.pos);
        const match = /^(#{1,6})[ \t]+/.exec(line.text);
        if (!match || context.pos - line.from < match[0].length) return null;
        // Le titre doit en être un pour l'analyseur : pas dans un bloc de code.
        const headings = readHeadings(context.state);
        const heading = headings.find((h) => h.from === line.from);
        if (!heading) return null;
        const from = line.from + match[0].length;
        const query = context.state.sliceDoc(from, context.pos);

        let results;
        if (heading.level === 1) {
            results = await fetchResults(urls.projects, { q: query }, context);
        } else {
            const above = pathAbove(headings, line, heading.level);
            if (!above) return null;
            results = await fetchResults(
                urls.sections,
                { projet: above.project, chemin: joinPath(above.path), q: query },
                context,
            );
        }
        if (!results?.length) return null;
        return {
            from,
            // La liste est déjà filtrée par le serveur (casse et accents ignorés).
            filter: false,
            options: results.map((result) => ({ label: result.name })),
        };
    };
}

function imageSource(urls) {
    return async (context) => {
        const before = context.state.sliceDoc(
            context.state.doc.lineAt(context.pos).from,
            context.pos,
        );
        const inPath = IMAGE_PATH_TRIGGER.exec(before);
        const created = inPath ?? IMAGE_TRIGGER.exec(before);
        if (!created) return null;
        const results = await fetchResults(urls.images, { q: inPath ? inPath[1] : created[1] }, context);
        if (!results?.length) return null;
        const from = context.pos - (inPath ? inPath[1].length : created[0].length);
        return {
            from,
            filter: false,
            options: results.map((image) => ({
                label: image.name,
                // Vignette affichée dans la liste (addToOptions).
                thumbnail: image.url,
                apply: (view, completion, start, end) => {
                    if (inPath) {
                        view.dispatch({
                            changes: { from: start, to: end, insert: image.name },
                            selection: { anchor: start + image.name.length },
                            userEvent: "input.complete",
                        });
                        return;
                    }
                    // ![](images/nom), le curseur entre les crochets pour la légende.
                    const text = `![](images/${image.name})`;
                    view.dispatch({
                        changes: { from: start, to: end, insert: text },
                        selection: EditorSelection.cursor(start + 2),
                        userEvent: "input.complete",
                    });
                },
            })),
        };
    };
}

function thumbnail(completion) {
    if (!completion.thumbnail) return null;
    const img = document.createElement("img");
    img.src = completion.thumbnail;
    img.alt = "";
    img.loading = "lazy";
    img.className = "mr-2 inline-block size-8 rounded border border-slate-300 bg-white object-contain";
    return img;
}

// Tab complète, comme dans VS Code : la suggestion choisie, ou la première si on n'a pas
// pris les flèches. Sans liste ouverte, Tab garde son rôle (passer au champ suivant).
function acceptWithTab(view) {
    if (completionStatus(view.state) !== "active") return false;
    if (!selectedCompletion(view.state)) moveCompletionSelection(true)(view);
    return acceptCompletion(view);
}

/** Extensions de CodeMirror ; `urls` : adresses des trois listes (#90). */
export function suggestions(urls) {
    return [
        EditorState.phrases.of(phrases),
        Prec.highest(keymap.of([{ key: "Tab", run: acceptWithTab }])),
        autocompletion({
            override: [titleSource(urls), imageSource(urls)],
            // Rien n'est choisi tant qu'on n'a pas pris les flèches : Entrée écrit un
            // nom nouveau en passant à la ligne, sans accepter une suggestion.
            selectOnOpen: false,
            // Tab juste après l'ouverture de la liste doit déjà compléter.
            interactionDelay: 0,
            icons: false,
            addToOptions: [{ render: thumbnail, position: 10 }],
        }),
    ];
}
