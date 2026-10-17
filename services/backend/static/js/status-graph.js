// Status tab state chart: the record's statuses as cards and the actions between them as edges,
// drawn with React Flow.
//
// Layout: the main statuses in one row in their order, side states (rejected, failed, archived, …) in
// a row below. Edges between neighbours are short arrows; every other edge runs orthogonally in its
// own lane: forward jumps above the row, backward edges and edges to/from side states in the band
// below. Lanes are assigned so that edges never share a segment, and labels sit on their edge's lane.
//
// The default view is focused: the main path, the actions leaving the current status (possible,
// blocked, automatic, done elsewhere; labelled) and the transitions the record took. "All transitions"
// adds every other declared transition (unlabelled; hover for the actions).
//
// Loaded as an ES module from the Status tab; React and React Flow come from esm.sh with pinned
// versions (one shared React, see ?deps). Data: GET /htmx/status/{entity}/{id}/statechart.

const REACT = "https://esm.sh/react@18.3.1";
const REACT_DOM = "https://esm.sh/react-dom@18.3.1/client?deps=react@18.3.1";
const XYFLOW = "https://esm.sh/@xyflow/react@12.3.6?deps=react@18.3.1,react-dom@18.3.1";
const XYFLOW_CSS = "https://cdn.jsdelivr.net/npm/@xyflow/react@12.3.6/dist/style.css";

const CARD_WIDTH = 150;
const CARD_HEIGHT = 46;
const GAP = 44;             // between neighbouring cards
const LANE = 26;            // between lanes
const LANE_START = 20;      // from a card to its first lane
const PORT_FIRST = 14;      // from a card's centre to its first port
const PORT = 11;            // between ports on one side of a card
const SIDE_GAP = 36;        // between side states
const LABEL_FONT = "12px system-ui, -apple-system, 'Segoe UI', sans-serif";
const LABEL_HEIGHT = 20;
const CORNER = 7;

const EDGE_STYLE = {
    available: { stroke: "#198754", strokeWidth: 2.25 },
    automatic: { stroke: "#0d6efd", strokeWidth: 2, strokeDasharray: "6 4" },
    blocked: { stroke: "#dc3545", strokeWidth: 2, strokeDasharray: "3 4" },
    elsewhere: { stroke: "#6c757d", strokeWidth: 2 },
    taken: { stroke: "#495057", strokeWidth: 2.25 },
    main: { stroke: "#adb5bd", strokeWidth: 1.5 },
    other: { stroke: "#ced4da", strokeWidth: 1.25 },
};
const LOUD = new Set(["available", "automatic", "blocked", "elsewhere"]);
const STATE_TEXT = {
    available: "possible now",
    automatic: "automatic (status worker)",
    blocked: "blocked",
    elsewhere: "done from another page",
    inactive: "",
};

let modulesPromise = null;

function loadModules() {
    if (!modulesPromise) {
        if (!document.querySelector(`link[href="${XYFLOW_CSS}"]`)) {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = XYFLOW_CSS;
            document.head.appendChild(link);
        }
        injectStyles();
        modulesPromise = Promise.all([import(REACT), import(REACT_DOM), import(XYFLOW)]).catch((err) => {
            modulesPromise = null;
            throw err;
        });
    }
    return modulesPromise;
}

function injectStyles() {
    if (document.getElementById("status-chart-styles")) return;
    const style = document.createElement("style");
    style.id = "status-chart-styles";
    style.textContent = `
        .sc-wrap { display: flex; flex-direction: column; height: 100%; }
        .sc-bar { display: flex; align-items: center; gap: 4px; padding: 4px 6px; font-size: 12px; }
        .sc-bar button { border: 1px solid var(--bs-border-color, #dee2e6); background: var(--bs-body-bg, #fff); color: var(--bs-body-color, #212529);
                         border-radius: 4px; width: 24px; height: 22px; line-height: 1; padding: 0; }
        .sc-bar label { margin-left: auto; user-select: none; color: var(--bs-secondary-color, #6c757d); }
        .sc-bar input { margin-right: 4px; vertical-align: -2px; }
        .sc-flow { flex: 1; min-height: 0; }
        .sc-card { width: ${CARD_WIDTH}px; height: ${CARD_HEIGHT}px; padding: 0 8px; border-radius: 8px; font-size: 13px; line-height: 1.2;
                   display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
                   background: var(--bs-body-bg, #fff); border: 1px solid var(--bs-border-color, #dee2e6); color: var(--bs-secondary-color, #6c757d); }
        .sc-card.sc-visited { color: var(--bs-body-color, #212529); border-color: #adb5bd; }
        .sc-card.sc-current { color: #fff; background: var(--bs-primary, #0d6efd); border-color: var(--bs-primary, #0d6efd);
                              box-shadow: 0 0 0 4px rgba(13,110,253,.2); font-weight: 600; }
        .sc-card.sc-side { border-style: dashed; }
        .sc-meta { font-size: 11px; font-weight: normal; opacity: .85; margin-top: 1px; }
        .sc-label { position: absolute; transform: translate(-50%, -50%); pointer-events: all; font: ${LABEL_FONT}; white-space: nowrap;
                    height: ${LABEL_HEIGHT}px; line-height: ${LABEL_HEIGHT - 2}px; padding: 0 7px; border: 1px solid; border-radius: 9px;
                    background: var(--bs-body-bg, #fff); cursor: help; }
        .sc-empty { color: var(--bs-secondary-color, #6c757d); font-size: .875rem; }
    `;
    document.head.appendChild(style);
}

let measureContext = null;

function textWidth(text) {
    if (typeof document === "undefined") return text.length * 6;
    measureContext ??= document.createElement("canvas").getContext("2d");
    measureContext.font = LABEL_FONT;
    return Math.ceil(measureContext.measureText(text).width);
}

function tooltip(t) {
    return t.actions.map((a) => {
        const lines = [`${a.label} (${a.kind})${t.fromCurrent && STATE_TEXT[a.state] ? ": " + STATE_TEXT[a.state] : ""}`];
        a.blockers.forEach((b) => lines.push(`  waiting for: ${b}`));
        a.effects.forEach((e) => lines.push(`  also: ${e}`));
        return lines.join("\n");
    }).join("\n");
}

// Greedy interval colouring: shortest edges get the lanes nearest to the cards.
function assignLanes(items) {
    const lanes = [];
    for (const item of [...items].sort((a, b) => (a.hi - a.lo) - (b.hi - b.lo) || a.lo - b.lo)) {
        let k = 0;
        while (lanes[k]?.some((o) => item.lo < o.hi + 6 && o.lo < item.hi + 6)) k++;
        (lanes[k] ??= []).push(item);
        item.lane = k;
    }
    return lanes.length;
}

function roundedPath(points) {
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length - 1; i++) {
        const [p, c, n] = [points[i - 1], points[i], points[i + 1]];
        const r = Math.min(CORNER, Math.hypot(c.x - p.x, c.y - p.y) / 2, Math.hypot(n.x - c.x, n.y - c.y) / 2);
        const a = { x: c.x - Math.sign(c.x - p.x) * r, y: c.y - Math.sign(c.y - p.y) * r };
        const b = { x: c.x + Math.sign(n.x - c.x) * r, y: c.y + Math.sign(n.y - c.y) * r };
        d += ` L ${a.x} ${a.y} Q ${c.x} ${c.y} ${b.x} ${b.y}`;
    }
    const last = points[points.length - 1];
    return d + ` L ${last.x} ${last.y}`;
}

// Positions of cards, edge routes and labels for the chart data; `showAll` adds the transitions that
// are neither on the main path, from the current status nor taken by the record.
export function layoutChart(data, showAll, measure = textWidth) {
    const main = data.cards.filter((c) => !c.side).sort((a, b) => a.rank - b.rank);
    const column = new Map(main.map((c, i) => [c.id, i]));
    const role = (t) => {
        if (t.fromCurrent && LOUD.has(t.state)) return t.state;
        if (t.taken) return "taken";
        if (column.has(t.source) && column.get(t.target) === column.get(t.source) + 1) return "main";
        return "other";
    };
    const shown = data.transitions.map((t) => ({ t, role: role(t) })).filter((e) => showAll || e.role !== "other");
    const linked = new Set(shown.flatMap((e) => [e.t.source, e.t.target]));
    const side = data.cards.filter((c) => c.side && (c.current || c.visited || linked.has(c.id))).sort((a, b) => a.rank - b.rank);

    // labels: the first action of each loud edge, preferring one not already used on another edge
    const rank = new Map(data.cards.map((c) => [c.id, c.rank]));
    const used = new Set();
    for (const e of shown.filter((e) => LOUD.has(e.role)).sort((a, b) => rank.get(a.t.target) - rank.get(b.t.target))) {
        const action = e.t.actions.find((a) => !used.has(a.label)) || e.t.actions[0];
        used.add(action.label);
        const extra = e.t.actions.length - 1;
        e.label = { text: action.label + (extra ? ` +${extra}` : "") };
        e.label.width = measure(e.label.text) + 16;
    }

    // cards
    const pos = new Map();
    main.forEach((c, i) => pos.set(c.id, { x: i * (CARD_WIDTH + GAP), y: 0, side: false }));
    const centre = (id) => pos.get(id).x + CARD_WIDTH / 2;
    let free = -Infinity;
    for (const c of side
        .map((c) => {
            const xs = shown.filter((e) => (e.t.target === c.id && pos.has(e.t.source)) || (e.t.source === c.id && pos.has(e.t.target)))
                .map((e) => centre(e.t.target === c.id ? e.t.source : e.t.target));
            return { c, x: (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : CARD_WIDTH / 2) - CARD_WIDTH / 2 };
        })
        .sort((a, b) => a.x - b.x || a.c.rank - b.c.rank)) {
        const x = Math.max(c.x, free);
        pos.set(c.c.id, { x, y: null, side: true });
        free = x + CARD_WIDTH + SIDE_GAP;
    }

    // edge kinds and the x range each one occupies in its lane
    const above = [], band = [];
    for (const e of shown) {
        const s = pos.get(e.t.source), d = pos.get(e.t.target);
        const sx = centre(e.t.source), dx = centre(e.t.target);
        const dir = Math.sign(dx - sx);
        if (!s.side && !d.side) {
            const gap = column.get(e.t.target) - column.get(e.t.source);
            if (gap === 1 && !e.label) e.kind = "next";
            else if (gap > 0) { e.kind = "above"; above.push(e); }
            else { e.kind = "back"; band.push(e); }
        } else if (s.side && d.side) {
            e.kind = "next";
        } else {
            e.kind = s.side ? "up" : "down";
            // a straight drop only needs a lane for its label
            if (dir !== 0 || e.label) band.push(e);
        }
        e.lo = Math.min(sx, dx) + (dir === 0 ? 0 : PORT_FIRST);
        e.hi = Math.max(sx, dx) - (dir === 0 ? 0 : PORT_FIRST);
        e.dir = dir;
        if (e.label) {
            // the label sits in the middle of the lane segment and occupies the lane too
            const mid = (e.lo + e.hi) / 2;
            e.lo = Math.min(e.lo, mid - e.label.width / 2);
            e.hi = Math.max(e.hi, mid + e.label.width / 2);
        }
    }
    const lanesAbove = assignLanes(above);
    const lanesBand = assignLanes(band);
    const aboveY = (k) => -(LANE_START + k * LANE);
    const bandY = (k) => CARD_HEIGHT + LANE_START + k * LANE;
    const sideY = CARD_HEIGHT + (lanesBand ? LANE_START + (lanesBand - 1) * LANE + LANE_START + 6 : 44);
    for (const p of pos.values()) if (p.side) p.y = sideY;

    // ports: on the half of the card facing the other end; deeper lanes closer to the centre
    const ports = new Map();
    const addPort = (id, edge, end, face, half) => {
        const key = `${id}:${face}:${half}`;
        if (!ports.has(key)) ports.set(key, []);
        ports.get(key).push({ edge, end });
    };
    for (const e of shown) {
        if (e.kind === "next") continue;
        const face = { above: ["top", "top"], back: ["bottom", "bottom"], down: ["bottom", "top"], up: ["top", "bottom"] }[e.kind];
        addPort(e.t.source, e, "source", face[0], e.dir > 0 ? 1 : e.dir < 0 ? -1 : 0);
        addPort(e.t.target, e, "target", face[1], e.dir > 0 ? -1 : e.dir < 0 ? 1 : 0);
    }
    for (const [key, list] of ports) {
        const [id, , half] = key.split(":");
        list.sort((a, b) => (b.edge.lane ?? 0) - (a.edge.lane ?? 0));
        list.forEach((p, i) => { p.edge[p.end + "X"] = centre(id) + Number(half) * (PORT_FIRST + i * PORT); });
    }

    // routes and labels
    const edges = shown.map((e) => {
        const s = pos.get(e.t.source), d = pos.get(e.t.target);
        let points, label = null;
        if (e.kind === "next") {
            const forward = d.x > s.x;
            points = [{ x: forward ? s.x + CARD_WIDTH : s.x, y: s.y + CARD_HEIGHT / 2 }, { x: forward ? d.x : d.x + CARD_WIDTH, y: d.y + CARD_HEIGHT / 2 }];
        } else {
            const sy = { above: 0, back: CARD_HEIGHT, down: CARD_HEIGHT, up: sideY }[e.kind];
            const dy = { above: 0, back: CARD_HEIGHT, down: sideY, up: CARD_HEIGHT }[e.kind];
            const y = e.lane === undefined ? null : e.kind === "above" ? aboveY(e.lane) : bandY(e.lane);
            points = e.dir === 0
                ? [{ x: e.sourceX, y: sy }, { x: e.targetX, y: dy }]
                : [{ x: e.sourceX, y: sy }, { x: e.sourceX, y }, { x: e.targetX, y }, { x: e.targetX, y: dy }];
            if (e.label) label = { text: e.label.text, x: (e.sourceX + e.targetX) / 2, y };
        }
        return { id: e.t.id, transition: e.t, role: e.role, points, label };
    });

    const nodes = [...pos].map(([id, p]) => ({ id, x: p.x, y: p.y, card: data.cards.find((c) => c.id === id) }));
    const minY = lanesAbove ? aboveY(lanesAbove - 1) - LABEL_HEIGHT / 2 - 2 : -4;
    const maxY = side.length ? sideY + CARD_HEIGHT : lanesBand ? bandY(lanesBand - 1) + LABEL_HEIGHT / 2 + 2 : CARD_HEIGHT;
    const maxX = Math.max(...nodes.map((n) => n.x + CARD_WIDTH));
    return { nodes, edges, bounds: { x: -4, y: minY, width: maxX + 8, height: maxY - minY + 4 } };
}

export async function mountStatusGraph(container, url) {
    const [[React, ReactDOMClient, XY], response] = await Promise.all([loadModules(), fetch(url, { headers: { Accept: "application/json" } })]);
    if (!response.ok) throw new Error(`state chart request failed: ${response.status}`);
    const data = await response.json();
    if (!data.cards.length) {
        container.innerHTML = '<div class="sc-empty p-3">No statuses to show.</div>';
        return;
    }
    const focused = layoutChart(data, false);
    const full = layoutChart(data, true);
    const hasMore = full.edges.length > focused.edges.length;

    const h = React.createElement;
    const { ReactFlow, ReactFlowProvider, Handle, Position, MarkerType, EdgeLabelRenderer, useReactFlow } = XY;

    function StatusCard({ data: card }) {
        const css = ["sc-card", card.current && "sc-current", card.visited && "sc-visited", card.side && "sc-side"].filter(Boolean).join(" ");
        const hidden = { opacity: 0 };
        return h("div", { className: css, title: card.description || "" },
            h(Handle, { type: "target", position: Position.Left, style: hidden, isConnectable: false }),
            h("div", null, (card.visited && !card.current ? "✓ " : "") + card.label),
            card.current && card.since ? h("div", { className: "sc-meta" }, `since ${card.since}`) : null,
            h(Handle, { type: "source", position: Position.Right, style: hidden, isConnectable: false }),
        );
    }

    function ActionEdge({ id, markerEnd, style, data: e }) {
        const path = roundedPath(e.points);
        return h(React.Fragment, null,
            h("path", { d: path, fill: "none", stroke: "transparent", strokeWidth: 12, style: { pointerEvents: "stroke", cursor: "help" } },
                h("title", null, tooltip(e.transition))),
            h("path", { id, d: path, fill: "none", className: "react-flow__edge-path", style, markerEnd }),
            e.label ? h(EdgeLabelRenderer, null,
                h("div", {
                    className: "sc-label nodrag nopan",
                    style: { left: e.label.x, top: e.label.y, borderColor: style.stroke, color: style.stroke },
                    title: tooltip(e.transition),
                }, e.label.text)) : null,
        );
    }

    const order = { other: 0, main: 1, taken: 2 };
    const toFlow = (layout) => ({
        bounds: layout.bounds,
        nodes: layout.nodes.map((n) => ({
            id: n.id, type: "status", position: { x: n.x, y: n.y }, data: n.card, draggable: false, selectable: false,
        })),
        edges: [...layout.edges].sort((a, b) => (order[a.role] ?? 3) - (order[b.role] ?? 3)).map((e) => {
            const style = EDGE_STYLE[e.role];
            return {
                id: e.id, source: e.transition.source, target: e.transition.target, type: "action", data: e,
                style, selectable: false, focusable: false,
                markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke, width: 14, height: 14 },
            };
        }),
    });
    const views = { focused: toFlow(focused), full: toFlow(full) };

    function Chart() {
        const [showAll, setShowAll] = React.useState(false);
        const flow = useReactFlow();
        const view = showAll ? views.full : views.focused;
        const fit = () => flow.fitBounds(view.bounds, { padding: 0.02 });
        React.useLayoutEffect(() => {
            container.style.height = heightFor(view.bounds);
            const frame = requestAnimationFrame(fit);
            return () => cancelAnimationFrame(frame);
        }, [showAll]);
        return h("div", { className: "sc-wrap" },
            h("div", { className: "sc-bar" },
                h("button", { type: "button", title: "Zoom out", onClick: () => flow.zoomOut() }, "−"),
                h("button", { type: "button", title: "Zoom in", onClick: () => flow.zoomIn() }, "+"),
                h("button", { type: "button", title: "Fit", onClick: fit }, "⤢"),
                hasMore ? h("label", null,
                    h("input", { type: "checkbox", checked: showAll, onChange: (ev) => setShowAll(ev.target.checked) }),
                    "All transitions") : null,
            ),
            h("div", { className: "sc-flow" },
                h(ReactFlow, {
                    nodes: view.nodes, edges: view.edges, nodeTypes: { status: StatusCard }, edgeTypes: { action: ActionEdge },
                    nodesConnectable: false, nodesDraggable: false, elementsSelectable: false, minZoom: 0.3, maxZoom: 1.5,
                    onEdgeClick: () => {},
                    onInit: (instance) => instance.fitBounds(view.bounds, { padding: 0.02 }),
                    // let the page scroll over the chart; zoom with the buttons
                    zoomOnScroll: false, panOnScroll: false, preventScrolling: false, zoomOnDoubleClick: false,
                }),
            ),
        );
    }

    // the chart's height at the width it gets (plus the button bar)
    const heightFor = (bounds) => {
        const scale = Math.min(1, (container.clientWidth || 1000) / bounds.width);
        return `${Math.round(Math.min(Math.max(bounds.height * scale + 36, 130), 460))}px`;
    };
    container.innerHTML = "";
    container.style.height = heightFor(focused.bounds);
    ReactDOMClient.createRoot(container).render(h(ReactFlowProvider, null, h(Chart)));
}
