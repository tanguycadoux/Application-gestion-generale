// Capture rapide (#386) : Ctrl+Maj+K (⌘⇧K sur un Mac) ou le bouton de l'en-tête ouvre
// un dialogue qui ajoute une ligne à la note du jour, sans quitter la page. Le texte
// non envoyé reste dans le dialogue fermé.
(() => {
    const link = document.querySelector("[data-quick-capture]");
    const dialog = document.getElementById("quick-capture");
    if (!link || !dialog || !dialog.showModal) return;

    const form = dialog.querySelector("form");
    const plan = dialog.querySelector("[data-capture-plan]");
    const fields = dialog.querySelector("[data-capture-fields]");
    const openEditor = dialog.querySelector("[data-capture-open-editor]");
    const newTitle = form.elements.new_title;
    const newLabel = dialog.querySelector("[data-capture-new-label]");
    const titles = document.getElementById(newTitle.getAttribute("list"));
    const submit = form.querySelector('button[type="submit"]');
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    if (mac) link.title = "Capture rapide (⌘⇧K)";
    let sending = false;

    const target = () => form.querySelector('input[name="target"]:checked');

    // L'éditeur de la note du jour, ouvert dans cette page : une ligne ajoutée à côté
    // rendrait son texte périmé.
    function editsToday(today) {
        const date = document.getElementById("note-form")?.elements.date;
        return Boolean(date) && date.value === today;
    }

    function showNewLabel() {
        const title = target()?.dataset.title;
        newLabel.textContent = title
            ? `Nouveau titre sous « ${title} » (facultatif)`
            : "Nouveau projet (facultatif)";
    }

    async function loadPlan() {
        const chosen = target()?.value ?? "";
        try {
            const response = await fetch(link.href, {
                headers: { "HX-Request": "true" },
            });
            if (!response.ok) return;
            // HTML de l'application, où Django a échappé les titres de la note.
            plan.innerHTML = await response.text();
        } catch {
            // Sans plan, la ligne peut encore aller en tête de la note.
            return;
        }
        // Le plan se recharge : le titre choisi le reste, s'il est encore là.
        const radios = [...form.querySelectorAll('input[name="target"]')];
        (radios.find((radio) => radio.value === chosen) ?? radios[0]).checked = true;
        showNewLabel();
        const today = plan.querySelector("[data-today]")?.dataset.today;
        const blocked = editsToday(today);
        openEditor.hidden = !blocked;
        fields.hidden = blocked;
        // La classe « flex » l'emporterait sur l'attribut hidden.
        fields.classList.toggle("flex", !blocked);
        submit.hidden = blocked;
        submit.classList.toggle("inline-flex", !blocked);
    }

    function open() {
        if (dialog.open) return;
        dialog.showModal();
        form.elements.text.focus();
        loadPlan();
    }

    link.addEventListener("click", (event) => {
        // Ctrl+clic, clic du milieu : le lien garde son sens.
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        open();
    });

    // En capture : l'éditeur CodeMirror supprime la ligne par le même raccourci.
    document.addEventListener(
        "keydown",
        (event) => {
            const modifier = mac ? event.metaKey : event.ctrlKey;
            if (!modifier || !event.shiftKey || event.altKey) return;
            if (event.key.toLowerCase() !== "k") return;
            event.preventDefault();
            event.stopImmediatePropagation();
            open();
        },
        true,
    );

    form.elements.close.addEventListener("click", () => dialog.close());

    form.elements.text.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
        event.preventDefault();
        if (!sending) form.requestSubmit();
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (sending || fields.hidden) return;
        sending = true;
        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { "HX-Request": "true" },
            });
            if (response.ok) {
                form.reset();
                showNewLabel();
                dialog.close();
                Toast.insert(await response.text());
            } else if (response.status === 422) {
                showError(await response.text());
                loadPlan();
            } else {
                showError("", "Rien n'est ajouté : le serveur a rencontré une erreur.");
            }
        } catch {
            showError("", "Rien n'est ajouté : le serveur ne répond pas.");
        } finally {
            sending = false;
        }
    });

    // Un dialogue modal cache les toasts de la page : l'erreur s'affiche dedans.
    function showError(html, text = "") {
        const parsed = new DOMParser().parseFromString(html, "text/html");
        const message =
            text || parsed.querySelector("[data-toast] p")?.textContent || "";
        let error = dialog.querySelector("[data-capture-error]");
        if (!error) {
            error = document.createElement("p");
            error.dataset.captureError = "";
            error.setAttribute("role", "alert");
            error.className = "text-red-800 [overflow-wrap:anywhere]";
            form.insertBefore(error, form.lastElementChild);
        }
        error.textContent = message;
    }

    dialog.addEventListener("close", () => {
        dialog.querySelector("[data-capture-error]")?.remove();
    });

    // Suggestions du nouveau titre : les projets, ou les niveaux sous le titre choisi
    // (listes de l'éditeur, #90).
    let timer = 0;
    let request = null;

    async function suggest() {
        request?.abort();
        request = new AbortController();
        const { project, path } = target()?.dataset ?? {};
        const query = { q: newTitle.value };
        const url = project ? newTitle.dataset.sectionsUrl : newTitle.dataset.projectsUrl;
        if (project) Object.assign(query, { project, path });
        try {
            const response = await fetch(`${url}?${new URLSearchParams(query)}`, {
                signal: request.signal,
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return;
            const data = await response.json();
            titles.replaceChildren(
                ...data.results.map(({ name }) => new Option(name, name)),
                ...(data.elsewhere ?? []).map(({ name, where }) => {
                    const option = new Option(name, name);
                    option.label = where;
                    return option;
                }),
            );
        } catch {
            // Requête annulée (la saisie a changé) ou serveur injoignable.
        }
    }

    newTitle.addEventListener("focus", suggest);
    newTitle.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(suggest, 150);
    });
    form.addEventListener("change", (event) => {
        if (event.target.name !== "target") return;
        showNewLabel();
        titles.replaceChildren();
    });
})();
