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

// ------------------------------------------------------------------------------------------------

const csrftoken = getCookie("csrftoken");

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".todo-toggle").forEach(todo_checkbox => {
        todo_checkbox.addEventListener("change", async () => {
            // Cocher une tâche met à jour l'avancement de ses ancêtres (#164) :
            // la page est rechargée pour les afficher.
            await toggle_todo(todo_checkbox.dataset.url, todo_checkbox.checked, csrftoken);
            location.reload();
        });
    });
});