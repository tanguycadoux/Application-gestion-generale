// Galerie des alertes (#156) : page de développement seulement. Les toasts n'ont pas de
// durée (`duration: null`), la confirmation se rouvre tant qu'on la ferme.
const LONG_MESSAGE =
    "Un message long, pour voir le retour à la ligne et la largeur maximale d'un toast : " +
    "une importation de plusieurs fichiers, dont un nom de fichier très long comme " +
    "capture-2026-10-27-153045-avec-un-nom-vraiment-beaucoup-trop-long.png, a échoué.";

function showToasts() {
    Alert.toast("Une information.", { type: "info", duration: null });
    Alert.toast("L'opération a réussi.", { type: "success", duration: null });
    Alert.toast("Un point d'attention.", { type: "warning", duration: null });
    Alert.toast("Quelque chose a échoué.", { type: "error", duration: null });
    Alert.toast(LONG_MESSAGE, { type: "info", duration: null });
}

const confirmButton = document.querySelector("#gallery-confirm button");

async function openConfirmation() {
    await Alert.confirmAt(confirmButton, "Supprimer définitivement cet élément ?");
}

showToasts();
document.querySelector("#gallery-toasts-again button").addEventListener("click", showToasts);
confirmButton.addEventListener("click", openConfirmation);
openConfirmation();
