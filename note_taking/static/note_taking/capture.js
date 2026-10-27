// Images collées (Ctrl+V) ou déposées (#196), importées sous un nom généré par le
// serveur (`capture-AAAA-MM-JJ-HHMMSS.png`). Partagé par l'éditeur et la page des images.

/** Les fichiers image d'un presse-papiers ou d'un dépôt ; vide si ce n'en est pas un. */
export function imageFiles(dataTransfer) {
    return [...(dataTransfer?.files ?? [])].filter((file) => file.type.startsWith("image/"));
}

/**
 * Envoie une image au serveur ; renvoie `{ name, reference, url }`. Une erreur métier
 * (contenu qui n'est pas une image, type refusé) devient une `Error` avec son message.
 * `notify` : la page va se recharger, le serveur y laisse un message à afficher.
 */
export async function uploadCapture(url, file, csrfToken, { notify = false } = {}) {
    const body = new FormData();
    body.append("image", file, file.name || "image.png");
    if (notify) body.append("notify", "1");
    let response;
    try {
        response = await fetch(url, {
            method: "POST",
            body,
            headers: { "X-CSRFToken": csrfToken, Accept: "application/json" },
        });
    } catch {
        const error = new Error("L'image n'a pas pu être envoyée : le serveur ne répond pas.");
        error.network = true;
        throw error;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error ?? "L'image n'a pas pu être importée.");
    return data;
}
