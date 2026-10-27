// Page des images (#196) : coller (Ctrl+V) ou déposer une image l'importe, puis la page
// se recharge pour la montrer. Les messages (succès ou refus) viennent du serveur, qui
// les laisse pour le rechargement.
import { imageFiles, uploadCapture } from "./capture.js";

const root = document.getElementById("image-capture");

async function importFiles(files) {
    for (const file of files) {
        try {
            await uploadCapture(root.dataset.captureUrl, file, root.dataset.csrf, { notify: true });
        } catch (error) {
            // Un refus est déjà noté par le serveur pour le rechargement ; une panne
            // réseau n'a pas de message : on l'affiche et on ne recharge pas.
            if (error.network) {
                window.Alert?.toast(error.message, { type: "error" });
                return;
            }
        }
    }
    window.location.reload();
}

if (root) {
    document.addEventListener("paste", (event) => {
        const files = imageFiles(event.clipboardData);
        if (!files.length) return;
        event.preventDefault();
        importFiles(files);
    });
    // Sans cela, le navigateur ouvre l'image déposée à la place de la page.
    document.addEventListener("dragover", (event) => {
        if ([...(event.dataTransfer?.types ?? [])].includes("Files")) event.preventDefault();
    });
    document.addEventListener("drop", (event) => {
        const files = imageFiles(event.dataTransfer);
        if (!files.length) return;
        event.preventDefault();
        importFiles(files);
    });
}
