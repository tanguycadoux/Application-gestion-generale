// Arbre des chemins en cases (#302, #433) : ce qui est coché est ce qui est cherché. Un
// niveau coché comprend tous ses sous-niveaux.
//
// - Sous une case cochée, celles des sous-niveaux sont cochées et grisées ; une case
//   grisée n'est pas envoyée avec le formulaire. Décocher rend à chacune son état d'avant.
// - Au-dessus d'une case cochée, celles des niveaux parents sont « partiellement
//   cochées » (`indeterminate`), et restent cliquables.
//
// Sans ce script, toutes les cases restent actives, et le serveur cherche la même chose.
(function () {
    "use strict";

    const BOX = ':scope > details > summary > input[type="checkbox"], :scope > div > input[type="checkbox"]';

    function labelOf(box) {
        const label = box.closest("li").querySelector(`label[for="${box.id}"]`);
        return label?.title || label?.textContent.trim() || "";
    }

    /** Met à jour le niveau `item`, compris dans le niveau nommé `cover` s'il y en a un.
     * Renvoie vrai si lui-même ou un de ses sous-niveaux est cherché. */
    function update(item, cover) {
        const box = item.querySelector(BOX);
        if (box && cover) {
            // L'état d'avant est gardé dans la page, pour le rendre au décochage.
            if (!box.disabled && box.checked) box.dataset.own = "";
            box.checked = true;
            box.indeterminate = false;
            box.disabled = true;
            box.title = `Compris dans « ${cover} »`;
        } else if (box?.disabled) {
            box.disabled = false;
            box.checked = "own" in box.dataset;
            delete box.dataset.own;
            box.removeAttribute("title");
        }

        const chosen = Boolean(box?.checked);
        const inside = cover || (chosen ? labelOf(box) : "");
        let partly = false;
        for (const child of item.querySelectorAll(":scope > details > ul > li")) {
            partly = update(child, inside) || partly;
        }
        if (box && !cover) box.indeterminate = !chosen && partly;
        return chosen || partly;
    }

    function updateTree(tree) {
        for (const item of tree.querySelectorAll(":scope > li")) update(item, "");
    }

    function updateAll() {
        document.querySelectorAll("[data-path-tree]").forEach(updateTree);
    }

    // En phase de capture : les cases sont à jour avant que le formulaire ne soit lu, par
    // htmx ou par un autre script.
    for (const type of ["input", "change"]) {
        document.addEventListener(
            type,
            (event) => {
                const tree = event.target.closest?.("[data-path-tree]");
                if (tree) updateTree(tree);
            },
            true,
        );
    }
    // Les cases que le navigateur ou htmx remettent après un retour en arrière.
    window.addEventListener("pageshow", updateAll);
    document.addEventListener("htmx:historyRestore", updateAll);
    updateAll();
})();
