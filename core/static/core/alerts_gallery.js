// Galerie des alertes (#156) : page de développement seulement.
//
// Les messages du serveur sont déjà dans la page. toasts.js fait disparaître les
// informations et les succès : ce script, `defer` comme lui mais placé plus haut dans
// la page, s'exécute le premier et leur retire `data-toast-autohide`, pour qu'ils
// restent à regarder.
document
    .querySelectorAll("#gallery-toasts [data-toast-autohide]")
    .forEach((toast) => toast.removeAttribute("data-toast-autohide"));

document
    .querySelector("#gallery-show-success button")
    .addEventListener("click", () => Toast.show("L'opération a réussi.", "success"));
document
    .querySelector("#gallery-show-error button")
    .addEventListener("click", () => Toast.show("Quelque chose a échoué.", "error"));

// La popover native de la confirmation, ouverte d'emblée : par un clic sur son bouton,
// pas par `showPopover()`, car sans bouton déclencheur elle n'a pas d'ancre et se place
// en haut à gauche de la page.
document.querySelector('[popovertarget="gallery-confirm"]').click();
