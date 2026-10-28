// Enregistrer la recherche en cours (#203). Les résultats se mettent à jour pendant
// la frappe (htmx) sans recharger la page : le formulaire d'enregistrement suit donc
// la zone de recherche, pour envoyer ce qui est affiché. Sans script, il envoie la
// requête de l'adresse.
(function () {
    "use strict";

    const save = document.querySelector("[data-saved-search-form]");
    const search = document.querySelector('form[method="get"] input[name="q"]');
    if (!save || !search) {
        return;
    }
    const hidden = save.querySelector('input[name="q"]');
    const name = save.querySelector('input[name="name"]');
    let proposed = name.value;

    search.addEventListener("input", () => {
        hidden.value = search.value.trim();
        // Le nom proposé suit la requête tant qu'on ne l'a pas modifié.
        if (name.value === proposed) {
            proposed = hidden.value.slice(0, name.maxLength);
            name.value = proposed;
        }
    });
})();
