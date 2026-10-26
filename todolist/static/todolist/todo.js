function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

async function toggle_todo(url, completed, csrftoken){
    return await fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrftoken,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            completed: completed
        })
    });
}

// Remplace chaque ligne modifiée (la tâche et ses ancêtres, #164) par sa version
// à jour, renvoyée par la vue : la position de défilement et l'état de la section
// « Terminées » sont conservés (#189).
function replaceRows(rows) {
    for (const [id, html] of Object.entries(rows)) {
        const row = document.querySelector(`tr[data-task-id="${id}"]`);
        if (row) {
            row.outerHTML = html;
        }
    }
}

// ------------------------------------------------------------------------------------------------

const csrftoken = getCookie("csrftoken");

// Délégation : les lignes remplacées gardent le comportement de leur case.
document.addEventListener("change", async (event) => {
    const checkbox = event.target;
    if (!checkbox.matches(".todo-toggle")) {
        return;
    }
    checkbox.disabled = true;
    let response = null;
    try {
        response = await toggle_todo(checkbox.dataset.url, checkbox.checked, csrftoken);
    } catch {
        // Serveur injoignable : traité comme un échec.
    }
    if (!response || !response.ok) {
        // La case revient à son état d'avant, et un toast le signale.
        checkbox.checked = !checkbox.checked;
        checkbox.disabled = false;
        Alert.toast("La tâche n'a pas pu être mise à jour.", { type: "error" });
        return;
    }
    if (checkbox.closest("table[data-live-rows]")) {
        replaceRows((await response.json()).rows);
    } else {
        // Détail d'une tâche : l'en-tête et la frise changent aussi.
        location.reload();
    }
});
