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
(() => {
    const form = document.getElementById("note-form");
    if (!form) return;

    const saveButton = document.querySelector(
        'button[form="note-form"][name="stay"]',
    );
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

    async function saveInPlace() {
        if (saving) return;
        saving = true;
        const sent = fields.map((field) => field.value);
        const data = new FormData(form);
        data.set("stay", "1");
        try {
            // Même en-tête que htmx : la vue répond par les toasts, sans redirection.
            const response = await fetch(form.action, {
                method: "POST",
                body: data,
                headers: { "HX-Request": "true" },
            });
            if (response.ok || response.status === 422) {
                Toast.insert(await response.text());
            } else {
                Toast.show(
                    "La note n'est pas enregistrée : le serveur a rencontré une erreur.",
                );
            }
            if (response.ok) {
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
        if (saveButton && event.submitter === saveButton && canSaveInPlace()) {
            event.preventDefault();
            saveInPlace();
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
