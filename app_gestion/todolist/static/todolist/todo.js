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

const csrftoken = getCookie("csrftoken");

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".todo-toggle").forEach(cb => {
        cb.addEventListener("change", async () => {
            const url = cb.dataset.url;

            await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrftoken,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    completed: cb.checked
                })
            });
        });
    });
});