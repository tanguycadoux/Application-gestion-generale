// Recherche dans les filtres à choix multiples des tableaux (#178, core/tables.py).
//
// Amélioration progressive : sans ce script, le champ de recherche reste caché et
// toutes les cases sont visibles. Avec lui, taper dans le champ masque les cases qui
// ne correspondent pas (casse et accents ignorés). Une case déjà cochée n'est jamais
// masquée : on voit toujours ce qui est choisi. Le focus va dans le champ à
// l'ouverture de la popover grâce à son attribut `autofocus`.

function fold(text) {
    return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

function setUpSearch(fieldset) {
    const box = fieldset.querySelector("[data-choice-search-box]");
    const input = box && box.querySelector("input");
    if (!input) return;
    const items = [...fieldset.querySelectorAll("[data-choice-item]")];
    const empty = fieldset.querySelector("[data-choice-empty]");

    function filter() {
        const query = fold(input.value.trim());
        let matching = 0;
        for (const item of items) {
            const matches = !query || fold(item.textContent).includes(query);
            const checked = item.querySelector("input[type=checkbox]").checked;
            item.hidden = !matches && !checked;
            if (matches) matching += 1;
        }
        // Rien ne correspond : le dire, même si des cases cochées restent affichées.
        empty.hidden = matching > 0;
    }

    input.addEventListener("input", filter);
    // Entrée dans le champ ne doit pas envoyer le formulaire à moitié rempli.
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") event.preventDefault();
    });
    box.hidden = false;
}

document.querySelectorAll("[data-choice-filter]").forEach(setUpSearch);
