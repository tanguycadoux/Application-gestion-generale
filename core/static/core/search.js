// Ctrl+K, ⌘K sur un Mac, met le curseur dans la barre de recherche du menu (#202).
// Quand elle n'est pas affichée (menu replié), il ouvre la page de recherche.
(() => {
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    if (mac) {
        for (const hint of document.querySelectorAll("[data-search-shortcut]")) {
            hint.textContent = "⌘ K";
        }
    }

    document.addEventListener("keydown", (event) => {
        const modifier = mac ? event.metaKey : event.ctrlKey;
        if (event.key.toLowerCase() !== "k" || !modifier || event.altKey || event.shiftKey) {
            return;
        }
        // offsetParent est nul pour un champ masqué (menu replié).
        const input = [...document.querySelectorAll("[data-search-input]")].find(
            (element) => element.offsetParent !== null,
        );
        const link = document.querySelector("[data-search-link]");
        if (input) {
            event.preventDefault();
            input.focus();
            input.select();
        } else if (link) {
            event.preventDefault();
            window.location.href = link.href;
        }
    });
})();
