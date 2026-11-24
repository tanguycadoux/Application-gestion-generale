// Échelle de la feuille d'une note (#421), comme l'affichage d'une page dans Word : quand
// la place manque, la feuille rétrécit en entier au lieu de se recomposer, et une ligne
// garde le même nombre de caractères. Sous MIN_ZOOM, le texte serait illisible : l'échelle
// s'arrête là, et la feuille se recompose. Sans ce script, elle se recompose toujours.
(function () {
    "use strict";

    // Un retour en arrière de htmx relance les scripts de la page : une seule mise en place.
    if (window.noteSheetStart) return window.noteSheetStart();

    // Largeur de la feuille : celle de la colonne du gabarit (240 mm), en pixels CSS.
    const SHEET_WIDTH = (240 * 96) / 25.4;
    // Texte de 16 px affiché à 11,2 px.
    const MIN_ZOOM = 0.7;

    let frame = null;

    function fit() {
        if (!frame) return;
        const ratio = frame.getBoundingClientRect().width / SHEET_WIDTH;
        // À un pixel près, la feuille est à sa taille : pas d'échelle de 0,999.
        const zoom = ratio > 0.998 ? 1 : Math.max(MIN_ZOOM, ratio);
        frame.style.setProperty("--note-zoom", zoom.toFixed(4));
    }

    // La place change avec la fenêtre, le plan et le menu ; la largeur du cadre ne dépend
    // pas de l'échelle (colonne de la grille, place de la barre de défilement réservée).
    // À l'image suivante : l'échelle change la hauteur du cadre, donc la mesure en cours.
    const observer = new ResizeObserver(() => requestAnimationFrame(fit));

    function setUp() {
        const found = document.querySelector("[data-note-frame]");
        if (found === frame) return;
        observer.disconnect();
        frame = found;
        fit();
        if (frame) observer.observe(frame);
    }

    window.noteSheetStart = setUp;
    setUp();
    // Un nouveau document de la recherche (#431), avant son premier affichage.
    document.addEventListener("htmx:afterSwap", setUp);
    document.addEventListener("htmx:historyRestore", setUp);
})();
