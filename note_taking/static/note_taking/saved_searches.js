// Enregistrer la recherche en cours (#203). Les résultats se mettent à jour pendant
// la frappe et quand on coche (htmx) sans recharger la page : le formulaire
// d'enregistrement suit donc la zone de recherche et les cases de l'arbre (#380),
// pour envoyer ce qui est affiché. Sans script, il envoie la recherche de l'adresse.
(function () {
    "use strict";

    const save = document.querySelector("[data-saved-search-form]");
    const searchForm = document.querySelector('search form[method="get"]');
    const search = searchForm?.querySelector('input[name="q"]');
    if (!save || !search) {
        return;
    }
    const hidden = save.querySelector('input[name="q"]');
    const filters = save.querySelector("[data-saved-search-filters]");
    const name = save.querySelector('input[name="name"]');
    const empty = document.querySelector("[data-saved-search-empty]");
    let proposed = name.value;

    // Le nom proposé sans texte : les projets et niveaux cochés, comme le serveur.
    function checkedLabels(checked) {
        return checked.map((box) => {
            const label = searchForm.querySelector(`label[for="${box.id}"]`);
            return label?.title || label?.textContent.trim() || "";
        });
    }

    function follow() {
        hidden.value = search.value.trim();
        const checked = [
            ...searchForm.querySelectorAll('input[type="checkbox"]:checked'),
        ].filter((box) => box.name === "projects" || box.name === "subjects");
        filters.replaceChildren(
            ...checked.map((box) => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = box.name;
                input.value = box.value;
                return input;
            }),
        );
        const nothing = !hidden.value && checked.length === 0;
        save.hidden = nothing;
        if (empty) {
            empty.hidden = !nothing;
        }
        // Le nom proposé suit la recherche tant qu'on ne l'a pas modifié.
        if (name.value === proposed) {
            const projectsFirst = [
                ...checked.filter((box) => box.name === "projects"),
                ...checked.filter((box) => box.name === "subjects"),
            ];
            proposed = (hidden.value || checkedLabels(projectsFirst).join(", "))
                .slice(0, name.maxLength);
            name.value = proposed;
        }
    }

    searchForm.addEventListener("input", follow);
    searchForm.addEventListener("change", follow);
})();
