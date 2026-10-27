// Recherche dans les filtres à choix multiples des tableaux (#178, core/tables.py).
//
// Amélioration progressive : sans ce script, le champ de recherche reste caché et
// la liste se replie et se déplie avec son <details> natif, toutes les cases y sont
// accessibles. Avec lui, le champ apparaît ; taper ouvre la liste et masque les cases
// qui ne correspondent pas (casse et accents ignorés). Une case déjà cochée n'est
// jamais masquée : on voit toujours ce qui est choisi. Le nombre de cases cochées du
// résumé suit les clics. Le focus va dans le champ à l'ouverture de la popover grâce
// à son attribut `autofocus`.

function fold(text) {
    return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

function setUpSearch(fieldset) {
    const box = fieldset.querySelector("[data-choice-search-box]");
    const input = box && box.querySelector("input");
    if (!input) return;
    const details = fieldset.querySelector("[data-choice-details]");
    const count = fieldset.querySelector("[data-choice-count]");
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
        // La recherche est active : la liste est ouverte pour voir ce qui correspond.
        if (query) details.open = true;
        // Rien ne correspond : le dire, même si des cases cochées restent affichées.
        empty.hidden = matching > 0;
    }

    function updateCount() {
        count.textContent = items.filter(
            (item) => item.querySelector("input[type=checkbox]").checked,
        ).length;
    }

    input.addEventListener("input", filter);
    // Entrée dans le champ ne doit pas envoyer le formulaire à moitié rempli.
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") event.preventDefault();
    });
    fieldset.addEventListener("change", updateCount);
    box.hidden = false;
}

document.querySelectorAll("[data-choice-filter]").forEach(setUpSearch);
