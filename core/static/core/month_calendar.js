// Calendrier mensuel (#276) : ← et → suivent les boutons « Mois précédent » et
// « Mois suivant » (aria-keyshortcuts), donc le même échange htmx de #calendar,
// historique compris. Sans JavaScript, les boutons restent des liens.
document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) {
        return;
    }
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
    }

    // Pendant la saisie, les flèches déplacent le curseur ou la sélection.
    const target = event.target;
    if (target instanceof Element && target.closest("input, textarea, select, [contenteditable]")) {
        return;
    }

    const link = document.querySelector(`#calendar a[aria-keyshortcuts="${event.key}"]`);
    if (link) {
        event.preventDefault();
        link.click();
    }
});
