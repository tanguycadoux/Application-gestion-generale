// Formulaire d'une note (#228) : Ctrl+S enregistre, et quitter la page avec des
// modifications non enregistrées demande confirmation au navigateur.
// Script classique, indépendant de CodeMirror (editor.js) : il fonctionne aussi sur
// le <textarea> seul, que l'éditeur tient à jour à chaque frappe.
(() => {
    const form = document.getElementById("note-form");
    if (!form) return;

    const fields = [form.elements.body, form.elements.date].filter(Boolean);
    const initial = fields.map((field) => field.value);
    // Une page rendue avec des erreurs affiche ce qui a été envoyé, pas ce qui est
    // enregistré : tout y est à enregistrer.
    const unsaved = form.hasAttribute("data-unsaved");
    let submitting = false;

    const isDirty = () =>
        unsaved || fields.some((field, i) => field.value !== initial[i]);

    form.addEventListener("submit", () => {
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
        form.requestSubmit();
    });
})();
