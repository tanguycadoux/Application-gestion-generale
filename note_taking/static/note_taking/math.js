// Formules LaTeX des notes (#99) : chaque <span class="math inline|display">
// produit par le rendu Markdown est affiché par KaTeX, à l'ouverture de la page
// et après chaque échange htmx (résultats de recherche, par exemple).
// Sans JavaScript, la formule reste lisible telle qu'écrite : \(…\) ou \[…\].
function renderMath(root) {
    for (const element of root.querySelectorAll("span.math:not([data-math-rendered])")) {
        // Le texte garde les délimiteurs de Pandoc : \( \) ou \[ \].
        const tex = element.textContent.slice(2, -2);
        katex.render(tex, element, {
            displayMode: element.classList.contains("display"),
            // Une formule invalide est affichée en rouge, sans bloquer les autres.
            throwOnError: false,
        });
        element.dataset.mathRendered = "true";
    }
}

document.addEventListener("DOMContentLoaded", () => renderMath(document.body));
document.addEventListener("htmx:load", (event) => renderMath(event.target));
