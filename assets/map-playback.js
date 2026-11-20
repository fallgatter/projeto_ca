function pauseWhileSeeking(event) {
    if (!event.target.closest("#map-progress")) return;
    if (document.getElementById("map-play")?.textContent !== "Pausar") return;

    // Stop scheduling frames immediately so a pending tick cannot mask the slider change.
    window.dash_clientside.set_props("map-tick", {disabled: true});
    window.dash_clientside.set_props("map-scrub", {data: performance.now()});
}

document.addEventListener("pointerdown", (event) => {
    if (event.button === 0) pauseWhileSeeking(event);
}, true);

document.addEventListener("keydown", (event) => {
    if (["Home", "End", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown"].includes(event.key)) {
        pauseWhileSeeking(event);
    }
}, true);

// Plotly redraws the axes at the end of a wheel gesture. Keep incoming figure
// patches out of the graph until that redraw and any drag have settled.
const mapPointers = new Set();
let mapGestureActive = false;
let mapGestureTimer;

function beginMapGesture() {
    clearTimeout(mapGestureTimer);
    if (!mapGestureActive) {
        mapGestureActive = true;
        window.dash_clientside.set_props("map-gesture", {data: true});
    }
}

function settleMapGesture() {
    clearTimeout(mapGestureTimer);
    if (mapPointers.size) return;
    mapGestureTimer = setTimeout(() => {
        mapGestureActive = false;
        window.dash_clientside.set_props("map-gesture", {data: false});
    }, 350);
}

let pendingWheel;
let wheelFrame = false;

async function drawWheelZoom() {
    const {plot, x, y, delta} = pendingWheel;
    pendingWheel = null;
    try {
        if (!plot.isConnected) return;
        const axes = [plot.layout.xaxis, plot.layout.yaxis];
        const spans = axes.map(axis => axis.range[1] - axis.range[0]);
        const maxFactor = Math.min(...axes.map((axis, i) => (axis.maxallowed - axis.minallowed) / spans[i]));
        const minFactor = maxFactor / 128;
        const factor = Math.max(minFactor, Math.min(maxFactor, Math.exp(delta)));
        const full = factor >= maxFactor - 1e-9;
        const ranges = axes.map((axis, i) => {
            if (full) return [axis.minallowed, axis.maxallowed];
            const span = spans[i] * factor;
            const anchor = [x, y][i];
            const min = Math.max(axis.minallowed,
                Math.min(axis.maxallowed - span, axis.range[0] + (spans[i] - span) * anchor));
            return [min, min + span];
        });
        if (ranges.some((range, i) => range.some((end, j) => Math.abs(end - axes[i].range[j]) > 1e-10))) {
            await window.Plotly.relayout(plot, {"xaxis.range": ranges[0], "yaxis.range": ranges[1]});
        }
    } finally {
        if (pendingWheel) {
            requestAnimationFrame(drawWheelZoom);
        } else {
            wheelFrame = false;
            settleMapGesture();
        }
    }
}

document.addEventListener("wheel", (event) => {
    const plot = event.target.closest(".map-graph .js-plotly-plot");
    const area = plot?.querySelector(".draglayer .nsewdrag");
    if (!area || !window.Plotly?.relayout || event.target.closest(".legend, .modebar")) return;
    if (![plot.layout?.xaxis, plot.layout?.yaxis].every(axis =>
        axis?.range?.every(Number.isFinite) && Number.isFinite(axis.minallowed) && Number.isFinite(axis.maxallowed))) return;

    const bounds = area.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (bounds.bottom - event.clientY) / bounds.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (mapPointers.size) return;

    beginMapGesture();
    const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? bounds.height : 1;
    const delta = Math.max(-0.45, Math.min(0.45, event.deltaY * multiplier / 550));
    pendingWheel = {plot, x, y, delta: delta + (pendingWheel?.plot === plot ? pendingWheel.delta : 0)};
    if (!wheelFrame) {
        wheelFrame = true;
        requestAnimationFrame(drawWheelZoom);
    }
}, {capture: true, passive: false});

document.addEventListener("pointerdown", (event) => {
    if (event.button === 0 && event.target.closest(".map-graph .draglayer")) {
        mapPointers.add(event.pointerId);
        beginMapGesture();
    }
}, true);

for (const eventName of ["pointerup", "pointercancel"]) {
    window.addEventListener(eventName, (event) => {
        if (mapPointers.delete(event.pointerId)) settleMapGesture();
    }, true);
}

document.addEventListener("click", (event) => {
    if (event.target.closest("#map-play")?.textContent === "Pausar") {
        window.dash_clientside.set_props("map-tick", {disabled: true});
    }
    if (event.target.closest(".map-graph .modebar-btn")) {
        beginMapGesture();
        settleMapGesture();
    }
}, true);

window.addEventListener("blur", () => {
    mapPointers.clear();
    if (mapGestureActive) settleMapGesture();
});

window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.mapPlayback = {
    capturePairViewport(baseline, adaptive, baselineFigure, adaptiveFigure, previous) {
        const changes = window.dash_clientside.callback_context.triggered;
        const fromAdaptive = changes[0]?.prop_id === "map-adaptive.relayoutData";
        return window.dash_clientside.mapPlayback.captureViewport(
            fromAdaptive ? adaptive : baseline,
            fromAdaptive ? adaptiveFigure : baselineFigure,
            previous,
        );
    },
    captureViewport(relayout, figure, previous) {
        const revision = figure?.layout?.uirevision;
        if (!relayout || !revision) return window.dash_clientside.no_update;

        const viewport = previous?.revision === revision ? {...previous} : {revision};
        let changed = false;
        for (const axis of ["xaxis", "yaxis"]) {
            const current = viewport[axis] || figure.layout[axis]?.range;
            if (!current) continue;

            const range = relayout[axis + ".range"] || [
                relayout[axis + ".range[0]"] ?? current[0],
                relayout[axis + ".range[1]"] ?? current[1],
            ];
            if (relayout[axis + ".autorange"] && viewport[axis]) {
                delete viewport[axis];
                changed = true;
            } else if (range.every(Number.isFinite) && (range[0] !== current[0] || range[1] !== current[1])) {
                viewport[axis] = range;
                changed = true;
            }
        }
        return changed ? viewport : window.dash_clientside.no_update;
    },
    renderMap(figure, gesturing, viewport) {
        if (gesturing || !figure) return window.dash_clientside.no_update;
        if (!viewport || viewport.revision !== figure.layout?.uirevision) return figure;

        const layout = {...figure.layout};
        for (const axis of ["xaxis", "yaxis"]) {
            if (viewport[axis]) layout[axis] = {...layout[axis], range: [...viewport[axis]], autorange: false};
        }
        return {...figure, layout};
    },
};
