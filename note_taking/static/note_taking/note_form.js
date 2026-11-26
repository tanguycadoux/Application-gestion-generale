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
// encadré propose de voir la version enregistrée ou de la remplacer. Il dit ce qui a
// modifié la note, et quand (#468, en-tête X-Note-Conflict), et ce qui a changé dans
// la version enregistrée (#471) : la vue compare le texte ouvert (`original`, tenu à
// jour à chaque enregistrement) à celui de la base.
//
// Fusion (#472) : si les deux modifications ne se touchent pas, la vue les réunit et
// enregistre ; la réponse porte le texte fusionné et les lignes venues d'ailleurs,
// que l'éditeur applique (merge.js). Sans éditeur, le <textarea> prend le texte
// fusionné s'il n'a pas changé depuis l'envoi.
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

    function showConflict(version, reason, html) {
        overwriteButton.value = version;
        if (reason) {
            conflict.querySelector("[data-conflict-reason]").textContent =
                decodeURIComponent(reason);
        }
        // Le HTML de la réponse, analysé sans rien exécuter, où Django a échappé le
        // texte de la note : les différences remplacent celles d'avant.
        const parsed = new DOMParser().parseFromString(html, "text/html");
        const changes = parsed.querySelector("template[data-conflict-changes]");
        const content = changes ? document.importNode(changes.content, true) : "";
        conflict.querySelector("[data-conflict-changes]")?.replaceChildren(content);
        conflict.hidden = false;
        conflict.scrollIntoView({ block: "nearest" });
    }

    // Les lignes venues d'ailleurs, dans l'éditeur ; faux si elles n'ont pas pu y
    // être mises, la page garde alors la version d'avant : l'enregistrement suivant
    // sera un conflit, plutôt que d'effacer ces lignes.
    function applyMerge(html, sent) {
        const original = form.elements.original;
        const parsed = new DOMParser().parseFromString(html, "text/html");
        const data = parsed.getElementById("note-merge");
        if (!data) {
            // Le texte enregistré est celui dont l'éditeur part désormais.
            if (original) original.value = sent;
            return true;
        }
        const { text, edits } = JSON.parse(data.textContent);
        const body = form.elements.body;
        const detail = { sent, edits, applied: false };
        body.dispatchEvent(new CustomEvent("note:merge", { detail }));
        if (!detail.applied && body.value === sent) {
            body.value = text;
            detail.applied = true;
        }
        if (!detail.applied) {
            Toast.show(
                "La note est enregistrée avec une modification faite ailleurs, que l'éditeur n'a pas pu reprendre. Rechargez la page avant de continuer.",
            );
            unsaved = true;
            return false;
        }
        saved = [text, ...saved.slice(1)];
        if (original) original.value = text;
        return true;
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
        form.elements.body.dispatchEvent(new CustomEvent("note:saving"));
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
            const html = await response.text();
            if (response.ok || response.status === 422 || response.status === 409) {
                Toast.insert(html);
            } else {
                Toast.show(
                    "La note n'est pas enregistrée : le serveur a rencontré une erreur.",
                );
            }
            if (response.status === 409) {
                showConflict(version, response.headers.get("X-Note-Conflict"), html);
            }
            if (response.ok) {
                saved = sent;
                unsaved = false;
                if (applyMerge(html, sent[0])) keepVersion(version);
                // Sans la nouvelle version (page et serveur dépareillés après une mise
                // à jour, #469), le prochain enregistrement serait refusé sans raison.
                if (form.elements.version && !version) {
                    Toast.show(
                        "La note est enregistrée, mais l'application a changé depuis l'ouverture de l'éditeur. Rechargez la page avant de continuer.",
                    );
                }
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
