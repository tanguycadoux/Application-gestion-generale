// Bouton « Copier le chemin » d'un lien vers un fichier local ou réseau (#496) : un
// navigateur n'ouvre pas un tel fichier, le chemin se colle dans l'Explorateur. Écouté
// sur le document : les résultats de recherche arrivent après le chargement (htmx).
(function () {
    "use strict";

    // Repli quand le presse-papiers asynchrone manque : il demande un contexte sécurisé
    // (`localhost` l'est, une adresse du réseau local en http ne l'est pas).
    function copyBySelection(text, button) {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch {
            copied = false;
        }
        area.remove();
        button.focus();
        return copied;
    }

    async function copy(text, button) {
        if (window.isSecureContext && navigator.clipboard) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch {
                // Refusé par le navigateur : le repli essaie encore.
            }
        }
        return copyBySelection(text, button);
    }

    document.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-copy-path]");
        if (!button) {
            return;
        }
        event.preventDefault();
        const path = button.dataset.copyPath;
        if (await copy(path, button)) {
            Toast.show("Chemin copié.", "success");
        } else {
            // Rien n'a pu être copié : le chemin, sélectionné, à copier à la main.
            window.prompt("Copier le chemin (Ctrl+C) :", path);
        }
    });
})();
