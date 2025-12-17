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

async function toggle_todo(url, completed, csrftoken, force=false){
    return await fetch(url, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrftoken,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            completed: completed,
            force: force
        })
    });
}

// ------------------------------------------------------------------------------------------------

const csrftoken = getCookie("csrftoken");

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".todo-toggle").forEach(todo_checkbox => {
        todo_checkbox.addEventListener("change", async () => {
            const response = await toggle_todo(todo_checkbox.dataset.url, todo_checkbox.checked, csrftoken);
            const data = await response.json()

            if (data.status === "needs_confirmation") {
                if (confirm(`Cette tâche contient ${data.children_count} sous-tâches non complétées. Voulez-vous tout compléter ?`)) {
                    await toggle_todo(todo_checkbox.dataset.url, todo_checkbox.checked, csrftoken, force=true);
                }
            }
            
            location.reload();
        });
    });
});