// Arbre « Projets et chemins » de la recherche (#380) : une réponse htmx remplace
// les compteurs et les marques `chemin:` de l'arbre, pas ses niveaux. Ouvrir les
// niveaux au-dessus d'un niveau marqué, comme le fait la page complète ; ceux que
// l'on a ouverts ou fermés soi-même ne sont jamais refermés.
(function () {
    "use strict";

    document.body.addEventListener("htmx:afterSettle", () => {
        for (const mark of document.querySelectorAll("[data-marked]")) {
            let details = mark.parentElement.closest("details");
            // Le compteur d'un niveau à sous-niveaux est dans son propre <summary>.
            if (details && mark.closest("summary")?.parentElement === details) {
                details = details.parentElement.closest("details");
            }
            while (details) {
                details.open = true;
                details = details.parentElement.closest("details");
            }
        }
    });
})();
