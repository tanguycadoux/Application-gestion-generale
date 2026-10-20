// Confirmation avant l'envoi d'un formulaire portant data-confirm="message" :
// une popover (Alert.confirmAt) s'ouvre à côté du bouton d'envoi.
// Sans JavaScript, le formulaire s'envoie directement.
document.addEventListener("submit", async (event) => {
    const form = event.target;
    const message = form.dataset.confirm;
    if (!message || form.dataset.confirmed === "true") {
        return;
    }

    event.preventDefault();
    const submitter = event.submitter;
    if (await Alert.confirmAt(submitter ?? form, message)) {
        form.dataset.confirmed = "true";
        form.requestSubmit(submitter);
    }
});
