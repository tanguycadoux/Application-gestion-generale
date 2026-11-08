// Notifications (django.contrib.messages) : bouton de fermeture, touche Échap, et
// succès qui disparaissent d'eux-mêmes. Sans ce script, elles restent sur la page.
// Reprise de research-paper-relationship-graph (static/js/toasts.js).
(function () {
    "use strict";

    const AUTOHIDE_DELAY = 6000;

    function setUp(toast) {
        const close = () => toast.remove();
        const button = toast.querySelector("[data-toast-close]");
        button.hidden = false;
        button.addEventListener("click", close);
        toast.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                close();
            }
        });
        if (toast.hasAttribute("data-toast-autohide")) {
            autohide(toast, close);
        }
    }

    function autohide(toast, close) {
        // En pause tant que le pointeur ou le focus clavier est sur le toast.
        let timer = setTimeout(close, AUTOHIDE_DELAY);
        const pause = () => clearTimeout(timer);
        const resume = () => {
            timer = setTimeout(close, AUTOHIDE_DELAY);
        };
        toast.addEventListener("mouseenter", pause);
        toast.addEventListener("mouseleave", resume);
        toast.addEventListener("focusin", pause);
        toast.addEventListener("focusout", resume);
    }

    // Toast créé par un script : le gabarit de base rend un modèle par niveau
    // (<template id="toast-template-error">), cloné ici ; le message est placé en
    // texte, jamais lu comme du HTML (#142).
    window.Toast = {
        show(message, level = "error") {
            const template = document.getElementById(`toast-template-${level}`);
            const toast = template.content.firstElementChild.cloneNode(true);
            toast.querySelector("p").textContent = message;
            document.getElementById("toasts").append(toast);
            setUp(toast);
        },

        // Toasts rendus par le serveur dans la réponse d'une requête en arrière-plan
        // (core/components/message_toasts.html, #389) : HTML de l'application, où
        // Django a déjà échappé le texte des messages. Le document analysé est
        // inerte (ni script ni chargement) ; seuls ses toasts sont repris.
        insert(html) {
            const parsed = new DOMParser().parseFromString(html, "text/html");
            const toasts = [...parsed.querySelectorAll("[data-toast]")];
            document.getElementById("toasts").append(...toasts);
            toasts.forEach(setUp);
        },
    };

    document.querySelectorAll("[data-toast]").forEach(setUp);
})();
