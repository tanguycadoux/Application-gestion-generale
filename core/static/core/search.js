// Ctrl+K, ⌘K sur un Mac, met le curseur dans la barre de recherche de l'en-tête (#202,
// #355). Sur la page de recherche, qui n'a pas cette barre, il va à sa zone de texte.
(() => {
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    if (mac) {
        for (const hint of document.querySelectorAll("[data-search-shortcut]")) {
            hint.textContent = "⌘ K";
        }
    }

    // offsetParent est nul pour un champ masqué.
    const visible = (selector) =>
        [...document.querySelectorAll(selector)].find((element) => element.offsetParent !== null);

    document.addEventListener("keydown", (event) => {
        const modifier = mac ? event.metaKey : event.ctrlKey;
        if (event.key.toLowerCase() !== "k" || !modifier || event.altKey || event.shiftKey) {
            return;
        }
        const input =
            visible("[data-search-input]") || visible('input[type="search"][name="q"]');
        if (input) {
            event.preventDefault();
            input.focus();
            input.select();
        }
    });
})();
