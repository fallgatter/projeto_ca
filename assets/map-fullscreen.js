function updateMapFullscreen() {
    const panel = document.getElementById("dashboard");
    const button = document.getElementById("map-fullscreen");
    if (!panel || !button) return;

    const expanded = document.fullscreenElement === panel || panel.classList.contains("is-expanded");
    button.setAttribute("aria-pressed", String(expanded));
    button.textContent = expanded ? "Sair da tela cheia" : "Tela cheia";
}

document.addEventListener("fullscreenchange", updateMapFullscreen);
document.addEventListener("click", async (event) => {
    const button = event.target.closest("#map-fullscreen");
    if (!button) return;

    const panel = document.getElementById("dashboard");
    if (document.fullscreenElement === panel) {
        await document.exitFullscreen();
    } else if (panel.classList.contains("is-expanded")) {
        panel.classList.remove("is-expanded");
    } else {
        try {
            await panel.requestFullscreen();
        } catch {
            panel.classList.add("is-expanded");
        }
    }
    updateMapFullscreen();
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const panel = document.getElementById("dashboard");
    if (panel?.classList.contains("is-expanded")) {
        panel.classList.remove("is-expanded");
        updateMapFullscreen();
        document.getElementById("map-fullscreen").focus();
    }
});
