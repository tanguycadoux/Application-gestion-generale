// Menu commun replié en icônes (#232). L'état est retenu dans localStorage ; s'il est
// indisponible (navigation privée, stockage bloqué), le menu marche, sans mémoire.
(() => {
    const KEY = "main-nav-collapsed";
    const nav = document.getElementById("main-nav");
    const toggle = document.getElementById("nav-toggle");
    if (!nav || !toggle) return;

    const read = () => {
        try {
            return localStorage.getItem(KEY) === "1";
        } catch {
            return false;
        }
    };
    const write = (collapsed) => {
        try {
            localStorage.setItem(KEY, collapsed ? "1" : "0");
        } catch {
            // Pas de mémoire : l'état ne survit pas à la page.
        }
    };
    const apply = (collapsed) => {
        nav.toggleAttribute("data-collapsed", collapsed);
        const label = collapsed ? "Déplier le menu" : "Replier le menu";
        toggle.setAttribute("aria-expanded", String(!collapsed));
        toggle.setAttribute("aria-label", label);
        toggle.title = label;
    };

    toggle.hidden = false;
    apply(read());
    toggle.addEventListener("click", () => {
        const collapsed = !nav.hasAttribute("data-collapsed");
        apply(collapsed);
        write(collapsed);
    });
})();
