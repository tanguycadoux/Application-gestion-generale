// Formulaire d'une note (#228) : Ctrl+S enregistre, et quitter la page avec des
// modifications non enregistrées demande confirmation au navigateur.
// Script classique, indépendant de CodeMirror (editor.js) : il fonctionne aussi sur
// le <textarea> seul, que l'éditeur tient à jour à chaque frappe.
//
// Enregistrement sur place (#389) : dans l'éditeur d'une note existante,
// « Enregistrer la note » (et Ctrl+S) envoie le formulaire en arrière-plan ; la
// page ne change pas (curseur, défilement, historique d'annulation), et les toasts
// rendus par le serveur s'ajoutent à la page. « Terminer l'édition » envoie le
// formulaire normalement. Sans ce script, « Enregistrer » revient à l'éditeur.
//
// Version ouverte (#386) : le formulaire dit quelle version de la note il a ouverte.
// Si elle a changé depuis, rien n'est enregistré (409) : le texte saisi reste, et un
// encadré propose de voir la version enregistrée ou de la remplacer.
(() => {
    const form = document.getElementById("note-form");
    if (!form) return;

    const saveButton = document.querySelector(
        'button[form="note-form"][name="stay"]',
    );
    const conflict = form.querySelector("[data-note-conflict]");
    const overwriteButton = conflict?.querySelector('button[name="overwrite"]');
    const fields = [form.elements.body, form.elements.date].filter(Boolean);
    let saved = fields.map((field) => field.value);
    // Une page rendue avec des erreurs affiche ce qui a été envoyé, pas ce qui est
    // enregistré : tout y est à enregistrer.
    let unsaved = form.hasAttribute("data-unsaved");
    let submitting = false;
    let saving = false;

    const isDirty = () =>
        unsaved || fields.some((field, i) => field.value !== saved[i]);

    // Une nouvelle note n'existe pas encore, et une date changée change l'adresse
    // de l'éditeur : ces enregistrements passent par la page suivante.
    const canSaveInPlace = () =>
        form.hasAttribute("data-save-in-place") &&
        (!form.elements.date || form.elements.date.value === saved[1]);

    function showConflict(version) {
        overwriteButton.value = version;
        conflict.hidden = false;
        conflict.scrollIntoView({ block: "nearest" });
    }

    function keepVersion(version) {
        if (!version || !form.elements.version) return;
        form.elements.version.value = version;
        conflict.hidden = true;
    }

    async function saveInPlace(overwrite) {
        if (saving) return;
        saving = true;
        const sent = fields.map((field) => field.value);
        const data = new FormData(form);
        data.set("stay", "1");
        if (overwrite) data.set("overwrite", overwrite);
        try {
            // Même en-tête que htmx : la vue répond par les toasts, sans redirection.
            const response = await fetch(form.action, {
                method: "POST",
                body: data,
                headers: { "HX-Request": "true" },
            });
            const version = response.headers.get("X-Note-Version");
            if (response.ok || response.status === 422 || response.status === 409) {
                Toast.insert(await response.text());
            } else {
                Toast.show(
                    "La note n'est pas enregistrée : le serveur a rencontré une erreur.",
                );
            }
            if (response.status === 409) showConflict(version);
            if (response.ok) {
                keepVersion(version);
                saved = sent;
                unsaved = false;
                const redirect = response.headers.get("HX-Redirect");
                if (redirect) {
                    submitting = true;
                    window.location.assign(redirect);
                }
            }
        } catch {
            Toast.show("La note n'est pas enregistrée : le serveur ne répond pas.");
        } finally {
            saving = false;
        }
    }

    form.addEventListener("submit", (event) => {
        const overwriting = overwriteButton && event.submitter === overwriteButton;
        const staying = saveButton && event.submitter === saveButton;
        if ((staying || overwriting) && canSaveInPlace()) {
            event.preventDefault();
            saveInPlace(overwriting ? overwriteButton.value : "");
            return;
        }
        submitting = true;
    });

    window.addEventListener("beforeunload", (event) => {
        if (submitting || !isDirty()) return;
        // Le navigateur affiche son propre message ; le texte n'est pas personnalisable.
        event.preventDefault();
        event.returnValue = "";
    });

    document.addEventListener("keydown", (event) => {
        const ctrl = event.ctrlKey || event.metaKey;
        if (!ctrl || event.altKey || event.shiftKey || event.key.toLowerCase() !== "s")
            return;
        event.preventDefault();
        form.requestSubmit(saveButton);
    });
})();
