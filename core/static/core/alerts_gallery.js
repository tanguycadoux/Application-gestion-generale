// Galerie des alertes (#156) : page de développement seulement. Les toasts n'ont pas de
// durée (`duration: null`) ; le bouton remplace ceux qui sont affichés (sinon les
// nouveaux s'empilent sous les anciens, hors de l'écran, et le bouton semble inerte).
const LONG_MESSAGE =
    "Un message long, pour voir le retour à la ligne et la largeur maximale d'un toast : " +
    "une importation de plusieurs fichiers, dont un nom de fichier très long comme " +
    "capture-2026-10-27-153045-avec-un-nom-vraiment-beaucoup-trop-long.png, a échoué.";

function showToasts() {
    document.getElementById("gallery-warning").hidden = true;
    document.querySelectorAll(".alert__toast").forEach((toast) => toast.remove());
    Alert.toast("Une information.", { type: "info", duration: null });
    Alert.toast("L'opération a réussi.", { type: "success", duration: null });
    Alert.toast("Un point d'attention.", { type: "warning", duration: null });
    Alert.toast("Quelque chose a échoué.", { type: "error", duration: null });
    Alert.toast(LONG_MESSAGE, { type: "info", duration: null });
}

// Un `alert_system.js` d'avant `duration: null`, resté dans le cache du navigateur,
// lit `null` comme 0 s : les toasts apparaissent puis disparaissent aussitôt. On le dit.
function warnIfToastsVanish() {
    setTimeout(() => {
        if (!document.querySelector(".alert__toast")) {
            document.getElementById("gallery-warning").hidden = false;
        }
    }, 800);
}

const confirmButton = document.querySelector("#gallery-confirm button");

async function openConfirmation() {
    await Alert.confirmAt(confirmButton, "Supprimer définitivement cet élément ?");
}

showToasts();
warnIfToastsVanish();
document.querySelector("#gallery-toasts-again button").addEventListener("click", () => {
    showToasts();
    warnIfToastsVanish();
});
confirmButton.addEventListener("click", openConfirmation);
openConfirmation();
