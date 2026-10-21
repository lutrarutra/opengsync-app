// Overview graph of a request, project or experiment: its records as columns, left to right (e.g.
// samples → libraries → pools → experiments), drawn with React Flow in a full-screen popup
// (templates/components/overview-graph.jinja2).
//
// Every node shows its status (colour, icon and label). Hover a node to trace its lineage (what it
// comes from and what it went into), click it to keep the trace. Column headers count the statuses;
// click one to trace every record in that status. The search box traces records by name.
//
// Samples and libraries of the same group (pool, lab prep or request) are bundled into one node with a
// status breakdown when their column is large; "+" expands a bundle, "−" on a member bundles it again.
//
// Data: GET …/overview (server/core/overview.py). React and React Flow come from esm.sh with the same
// pinned versions as status-graph.js.

const REACT = "https://esm.sh/react@18.3.1";
const REACT_DOM = "https://esm.sh/react-dom@18.3.1/client?deps=react@18.3.1";
const XYFLOW = "https://esm.sh/@xyflow/react@12.3.6?deps=react@18.3.1,react-dom@18.3.1";
const XYFLOW_CSS = "https://cdn.jsdelivr.net/npm/@xyflow/react@12.3.6/dist/style.css";

const MIN_NODE_WIDTH = 240; // px; nodes widen to fill the popup up to MAX_NODE_WIDTH, below MIN_NODE_WIDTH the graph zooms out
const MAX_NODE_WIDTH = 360;
const ITEM_HEIGHT = 50;
const BUNDLE_HEIGHT = 76;
const CHIPS_PER_ROW = 4;    // status chips in a column header
const LABEL_SIZE = 12;      // px; a long name shrinks down to LABEL_MIN_SIZE to fit, then is cut off
const LABEL_MIN_SIZE = 9;
const NODE_CHROME = 23;     // px; padding and borders of a node
const ASIDE_SIZE = 11;      // px; the muted aside next to a name (e.g. a pool's type)
const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const ROW_GAP = 8;
const COLUMN_GAP = 52;
const EXPAND_LIMIT = 30;    // a column with more records than this starts bundled
const PAD = 12;

const TONES = {
    draft: "#adb5bd",
    waiting: "#6ea8fe",
    progress: "#0d6efd",
    done: "#198754",
    failed: "#dc3545",
    inactive: "#6c757d",
};
const NO_STATUS = "#ced4da";
const ZOOM_KEY = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";  // React Flow's zoom activation key

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
    if (document.getElementById("overview-graph-styles")) return;
    const style = document.createElement("style");
    style.id = "overview-graph-styles";
    style.textContent = `
        .ov-wrap { position: absolute; inset: 0; display: flex; flex-direction: column; }
        .ov-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 0 0 6px; font-size: 12px; color: var(--bs-secondary-color, #6c757d); }
        .ov-bar input { font-size: 12px; padding: 2px 8px; height: 26px; width: 200px; border: 1px solid var(--bs-border-color, #dee2e6);
                        border-radius: 4px; background: var(--bs-body-bg, #fff); color: var(--bs-body-color, #212529); }
        .ov-bar button { font-size: 12px; height: 26px; padding: 0 8px; border: 1px solid var(--bs-border-color, #dee2e6); border-radius: 4px;
                         background: var(--bs-body-bg, #fff); color: var(--bs-body-color, #212529); }
        .ov-bar .ov-hint { margin-left: auto; }
        .ov-flow { flex: 1; min-height: 0; border: 1px solid var(--bs-border-color, #dee2e6); border-radius: 6px; }
        .ov-flow .react-flow__node { cursor: pointer; }
        .ov-node { width: var(--ov-node-width, ${MIN_NODE_WIDTH}px); padding: 5px 8px 5px 10px; border-radius: 6px; font-size: 12px; line-height: 1.35; position: relative; overflow: hidden;
                   font-family: ${FONT};
                   background: var(--bs-body-bg, #fff); color: var(--bs-body-color, #212529);
                   border: 1px solid var(--bs-border-color, #dee2e6); border-left: 4px solid var(--tone); transition: opacity .12s; }
        .ov-item { height: ${ITEM_HEIGHT}px; }
        .ov-bundle { height: ${BUNDLE_HEIGHT}px; background: var(--bs-tertiary-bg, #f8f9fa); border-left-color: var(--bs-secondary-color, #6c757d); }
        .ov-node.ov-seed { box-shadow: 0 0 0 2px var(--bs-primary, #0d6efd); }
        .ov-node.ov-pinned { box-shadow: 0 0 0 3px var(--bs-primary, #0d6efd); }
        .react-flow__node.ov-dim { opacity: .22; }
        .ov-row { display: flex; align-items: center; gap: 6px; min-width: 0; }
        .ov-label { font-weight: 600; white-space: nowrap; display: block; line-height: 18px; height: 18px; overflow: hidden; text-overflow: ellipsis; min-width: 0; color: inherit; text-decoration: none; }
        a.ov-label:hover { text-decoration: underline; }
        .ov-status { margin-left: auto; white-space: nowrap; flex-shrink: 0; color: var(--bs-secondary-color, #6c757d); }
        .ov-sub { color: var(--bs-secondary-color, #6c757d); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
        .ov-aside { margin-left: auto; white-space: nowrap; flex-shrink: 0; font-size: ${ASIDE_SIZE}px; color: var(--bs-secondary-color, #6c757d); }
        .ov-metric { white-space: nowrap; flex-shrink: 0; color: var(--bs-secondary-color, #6c757d); }
        .ov-btn { margin-left: auto; flex-shrink: 0; border: 1px solid var(--bs-border-color, #dee2e6); border-radius: 4px; background: var(--bs-body-bg, #fff);
                  color: var(--bs-body-color, #212529); font-size: 11px; line-height: 14px; padding: 0 5px; }
        .ov-item .ov-btn { position: absolute; top: 4px; right: 4px; display: none; }
        .ov-item:hover .ov-btn { display: block; }
        .ov-reads { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: var(--bs-secondary-bg, #e9ecef); }
        .ov-reads > div { height: 100%; background: ${TONES.done}; }
        .ov-reads.ov-low > div { background: #fd7e14; }
        .ov-bars { display: flex; gap: 2px; height: 8px; margin: 4px 0 3px; }
        .ov-bars > span { border-radius: 2px; min-width: 3px; }
        .ov-counts { color: var(--bs-secondary-color, #6c757d); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .ov-header { width: var(--ov-node-width, ${MIN_NODE_WIDTH}px); font-size: 12px; cursor: default; }
        .ov-header-title { font-weight: 600; font-size: 13px; color: var(--bs-body-color, #212529); }
        .ov-chips { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
        .ov-chip { border: 1px solid var(--bs-border-color, #dee2e6); border-radius: 10px; padding: 0 6px; background: var(--bs-body-bg, #fff);
                   color: var(--bs-body-color, #212529); font-size: 11px; line-height: 17px; display: inline-flex; align-items: center; gap: 3px; }
        .ov-chip.ov-active { border-color: var(--bs-primary, #0d6efd); box-shadow: 0 0 0 1px var(--bs-primary, #0d6efd); }
        .ov-flow .react-flow__edge-text { font-size: 11px; fill: var(--bs-secondary-color, #6c757d); }
        .ov-flow .react-flow__edge-textbg { fill: var(--bs-body-bg, #fff); }
        .ov-lanes { position: absolute; display: flex; flex-wrap: wrap; gap: 2px; max-width: ${COLUMN_GAP - 6}px; pointer-events: all; cursor: default;
                    font-family: ${FONT}; transition: opacity .12s; }
        .ov-lane { border-radius: 3px; padding: 0 4px; font-size: 10px; line-height: 14px; font-weight: 600; white-space: nowrap;
                   background: var(--bs-secondary-bg, #e9ecef); color: var(--bs-body-color, #212529); border: 1px solid var(--bs-border-color, #dee2e6); }
        .ov-empty { color: var(--bs-secondary-color, #6c757d); font-size: .875rem; padding: 1rem 0; }
    `;
    document.head.appendChild(style);
}

// ── model ───────────────────────────────────────────────────────────────────────────────────────

function prepare(data) {
    const column = new Map(data.columns.map((c, i) => [c.kind, i]));
    const nodes = data.nodes.map((n, order) => ({ ...n, order, col: column.get(n.kind) }));
    const groups = new Map();
    for (const n of nodes) {
        if (!n.group) continue;
        n.groupKey = `${n.kind}:${n.group}`;
        if (!groups.has(n.groupKey)) groups.set(n.groupKey, []);
        groups.get(n.groupKey).push(n);
    }
    const perKind = new Map();
    nodes.forEach((n) => perKind.set(n.kind, (perKind.get(n.kind) ?? 0) + 1));
    const bundleable = new Set([...groups].filter(([, members]) => members.length > 1).map(([key]) => key));
    const bundled = new Set([...bundleable].filter((key) => perKind.get(groups.get(key)[0].kind) > EXPAND_LIMIT));
    const status = (n) => (n.status === undefined ? null : data.statuses[n.kind]?.[n.status] ?? null);
    const href = (n) => (data.links[n.kind] ? data.links[n.kind].replace("{id}", n.ref) : null);
    // room for the column headers: title, status bar and the status chips
    const chips = Math.max(0, ...data.columns.map((c) => new Set(nodes.filter((n) => n.kind === c.kind && n.status !== undefined).map((n) => n.status)).size));
    const headerHeight = 34 + Math.ceil(chips / CHIPS_PER_ROW) * 21;
    return { data, nodes, groups, bundleable, bundled, status, href, headerHeight };
}

// Records → units (a record, or a bundle of records), edges between units, and their positions.
function layout(model, bundled, nodeWidth) {
    const { data, nodes } = model;
    const units = new Map();
    const unitOf = new Map();
    for (const n of nodes) {
        const id = n.groupKey && bundled.has(n.groupKey) ? `bundle:${n.groupKey}` : n.id;
        if (!units.has(id)) {
            units.set(id, {
                id, kind: n.kind, col: n.col, order: n.order, members: [], bundle: id !== n.id,
                groupKey: model.bundleable.has(n.groupKey) ? n.groupKey : null,
            });
        }
        units.get(id).members.push(n);
        unitOf.set(n.id, id);
    }

    const edges = new Map();
    for (const e of data.edges) {
        const source = unitOf.get(e.source), target = unitOf.get(e.target);
        const key = `${source}->${target}`;
        if (!edges.has(key)) edges.set(key, { id: key, source, target, count: 0, labels: new Set(), lanes: new Set() });
        const edge = edges.get(key);
        edge.count += 1;
        if (e.label) edge.labels.add(e.label);
        for (const lane of e.lanes ?? []) edge.lanes.add(lane);
    }
    const left = new Map(), right = new Map();
    for (const e of edges.values()) {
        if (!right.has(e.source)) right.set(e.source, []);
        if (!left.has(e.target)) left.set(e.target, []);
        right.get(e.source).push({ id: e.target, w: e.count });
        left.get(e.target).push({ id: e.source, w: e.count });
    }

    // order within columns: barycentre sweeps, starting from the right (records follow their pools)
    const columns = data.columns.map(() => []);
    for (const u of units.values()) columns[u.col].push(u);
    columns.forEach((col) => col.sort((a, b) => a.order - b.order));
    const rank = new Map();
    const reindex = (col) => col.forEach((u, i) => rank.set(u.id, (i + 0.5) / col.length));
    columns.forEach(reindex);
    const sweep = (col, neighbours) => {
        const key = new Map(col.map((u) => {
            const ns = neighbours.get(u.id) ?? [];
            if (!ns.length) return [u.id, rank.get(u.id)];
            let sum = 0, weight = 0;
            for (const n of ns) { sum += rank.get(n.id) * n.w; weight += n.w; }
            return [u.id, sum / weight];
        }));
        col.sort((a, b) => key.get(a.id) - key.get(b.id) || rank.get(a.id) - rank.get(b.id));
        reindex(col);
    };
    for (let pass = 0; pass < 3; pass++) {
        for (let c = columns.length - 2; c >= 0; c--) sweep(columns[c], right);
        for (let c = 1; c < columns.length; c++) sweep(columns[c], left);
    }
    for (let c = columns.length - 2; c >= 0; c--) sweep(columns[c], right);

    // heights: the tallest column is stacked, the others sit next to their neighbours
    const height = (u) => (u.bundle ? BUNDLE_HEIGHT : ITEM_HEIGHT);
    const pos = new Map();
    const total = (col) => col.reduce((s, u) => s + height(u) + ROW_GAP, 0);
    const anchor = columns.reduce((best, col, i) => (total(col) > total(columns[best]) ? i : best), 0);
    const place = (c, neighbours) => {
        let bottom = -ROW_GAP;
        for (const u of columns[c]) {
            const ns = (neighbours?.get(u.id) ?? []).filter((n) => pos.has(n.id));
            let top = bottom + ROW_GAP;
            if (ns.length) {
                let sum = 0, weight = 0;
                for (const n of ns) { const p = pos.get(n.id); sum += (p.y + p.h / 2) * n.w; weight += n.w; }
                top = Math.max(top, sum / weight - height(u) / 2);
            }
            pos.set(u.id, { x: c * (nodeWidth + COLUMN_GAP), y: top, h: height(u) });
            bottom = top + height(u);
        }
    };
    place(anchor, null);
    for (let c = anchor + 1; c < columns.length; c++) place(c, left);
    for (let c = anchor - 1; c >= 0; c--) place(c, right);

    let maxY = 0;
    for (const p of pos.values()) maxY = Math.max(maxY, p.y + p.h);
    const width = columns.length * nodeWidth + (columns.length - 1) * COLUMN_GAP;
    return {
        units, edges, pos, left, right,
        bounds: { x: -PAD, y: -model.headerHeight - PAD, width: width + 2 * PAD, height: maxY + model.headerHeight + 2 * PAD },
    };
}

// Units traced from the seeds: everything they come from and everything they went into.
function trace(view, seeds) {
    const units = new Set(seeds), edges = new Set();
    const walk = (start, neighbours, forward) => {
        const seen = new Set([start]), stack = [start];
        while (stack.length) {
            const id = stack.pop();
            for (const n of neighbours.get(id) ?? []) {
                edges.add(forward ? `${id}->${n.id}` : `${n.id}->${id}`);
                if (seen.has(n.id)) continue;
                seen.add(n.id);
                units.add(n.id);
                stack.push(n.id);
            }
        }
    };
    for (const id of seeds) { walk(id, view.right, true); walk(id, view.left, false); }
    return { units, edges };
}

function countStatuses(model, members) {
    const counts = new Map();
    for (const n of members) {
        const key = n.status === undefined ? "" : String(n.status);
        counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts].sort((a, b) => Number(a[0] || -1) - Number(b[0] || -1)).map(([key, count]) => {
        const status = key === "" ? null : model.data.statuses[members[0].kind]?.[key] ?? null;
        return { key, count, status, color: status ? TONES[status.tone] : NO_STATUS };
    });
}

let measureContext = null;

function textWidth(text, font) {
    measureContext ??= document.createElement("canvas").getContext("2d");
    measureContext.font = font;
    return measureContext.measureText(text).width;
}

// 1, 2, 3, 5 → ["1–3", "5"]
function laneRuns(lanes) {
    const runs = [];
    for (const lane of lanes) {
        const last = runs[runs.length - 1];
        if (last && lane === last[1] + 1) last[1] = lane;
        else runs.push([lane, lane]);
    }
    return runs.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`));
}

// width of the nodes that fills the canvas with all columns at 1:1, within MIN_NODE_WIDTH–MAX_NODE_WIDTH
function nodeWidthFor(canvasWidth, columns) {
    const fill = Math.floor((canvasWidth - 2 - 2 * PAD - (columns - 1) * COLUMN_GAP) / columns);
    return Math.max(MIN_NODE_WIDTH, Math.min(MAX_NODE_WIDTH, fill));
}

// font size that fits a name on its row next to its aside (names of libraries and samples are often long)
function labelSize(label, aside, nodeWidth) {
    const room = nodeWidth - NODE_CHROME - (aside ? textWidth(aside, `${ASIDE_SIZE}px ${FONT}`) + 6 : 0);
    let size = LABEL_SIZE;
    while (size > LABEL_MIN_SIZE && textWidth(label, `600 ${size}px ${FONT}`) > room) size -= 0.5;
    return size;
}

function readsText(n) {
    return n >= 1e9 ? `${(n / 1e9).toFixed(1)} G` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} k` : `${n}`;
}

// ── mount ───────────────────────────────────────────────────────────────────────────────────────

async function fetchData(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`overview request failed: ${response.status}`);
    return response.json();
}

function render(container, [React, ReactDOMClient, XY], data) {
    container.innerHTML = "";
    if (!data.nodes.length) {
        container.innerHTML = '<div class="ov-empty">Nothing to show yet.</div>';
        return;
    }
    const model = prepare(data);
    const h = React.createElement;
    const { ReactFlow, ReactFlowProvider, Handle, Position, MiniMap, useReactFlow, BaseEdge, EdgeLabelRenderer, getBezierPath } = XY;
    const hidden = { opacity: 0, pointerEvents: "none" };
    const plural = new Map(data.columns.map((c) => [c.kind, c.label.toLowerCase()]));

    const tooltip = (n) => {
        const status = model.status(n);
        return [n.label, status ? `Status: ${status.label} ${status.icon}` : null, ...(n.facts ?? []).map(([k, v]) => `${k}: ${v}`)]
            .filter(Boolean).join("\n");
    };

    function ReadsBar({ reads, requested }) {
        if (!requested || reads === undefined) return null;
        const share = reads / requested;
        return h("div", { className: "ov-reads" + (share < 0.8 ? " ov-low" : ""), title: `${readsText(reads)} of ${readsText(requested)} requested reads` },
            h("div", { style: { width: `${Math.min(100, share * 100)}%` } }));
    }

    function StatusBars({ counts }) {
        const total = counts.reduce((s, c) => s + c.count, 0);
        return h("div", { className: "ov-bars" }, counts.map((c) => h("span", {
            key: c.key, style: { flex: `${c.count / total} 1 0`, background: c.color },
            title: `${c.status ? `${c.status.label} ${c.status.icon}` : "no status"}: ${c.count}`,
        })));
    }

    function ItemNode({ data: d }) {
        const n = d.unit.members[0];
        const status = model.status(n);
        const href = model.href(n);
        const group = d.unit.groupKey ? model.groups.get(d.unit.groupKey) : null;
        const label = { className: "ov-label", style: { fontSize: `${d.labelSize}px` } };
        // name and its aside (on the right edge) on the first row; subtitle, sequenced reads and status (on the right edge) on the second
        return h("div", {
            className: `ov-node ov-item${d.seed ? " ov-seed" : ""}${d.pinned ? " ov-pinned" : ""}`,
            style: { "--tone": status ? TONES[status.tone] : NO_STATUS }, title: tooltip(n),
        },
            h(Handle, { type: "target", position: Position.Left, style: hidden, isConnectable: false }),
            h("div", { className: "ov-row" },
                href ? h("a", { ...label, className: "ov-label nodrag", href, onClick: (ev) => ev.stopPropagation() }, n.label) : h("span", label, n.label),
                n.aside ? h("span", { className: "ov-aside" }, n.aside) : null),
            h("div", { className: "ov-row" },
                h("span", { className: "ov-sub" }, n.sub ?? "\u00a0"),
                n.metrics?.reads !== undefined ? h("span", { className: "ov-metric" }, `${n.sub ? "· " : ""}${readsText(n.metrics.reads)} reads`) : null,
                status ? h("span", { className: "ov-status" }, `${status.label} ${status.icon}`) : null),
            group ? h("button", {
                type: "button", className: "ov-btn nodrag", title: `Bundle the ${group.length} ${plural.get(n.kind)} of ${data.groups[n.group]}`,
                onClick: (ev) => { ev.stopPropagation(); d.toggle(d.unit.groupKey, d.unit.id); },
            }, "−") : null,
            h(ReadsBar, n.metrics ?? {}),
            h(Handle, { type: "source", position: Position.Right, style: hidden, isConnectable: false }),
        );
    }

    function BundleNode({ data: d }) {
        const members = d.unit.members;
        const counts = countStatuses(model, members);
        const first = members[0];
        let reads = 0, requested = 0, withReads = false;
        for (const n of members) {
            if (n.metrics?.reads !== undefined) { reads += n.metrics.reads; withReads = true; }
            if (n.metrics?.requested) requested += n.metrics.requested;
        }
        const types = new Map();
        members.forEach((n) => n.sub && types.set(n.sub, (types.get(n.sub) ?? 0) + 1));
        const typeText = [...types].map(([t, c]) => `${c} ${t}`).join(" · ");
        const statusText = counts.map((c) => `${c.count} ${c.status ? c.status.label.toLowerCase() : "no status"}`).join(", ");
        return h("div", {
            className: `ov-node ov-bundle${d.seed ? " ov-seed" : ""}${d.pinned ? " ov-pinned" : ""}`,
            title: [`${members.length} ${plural.get(first.kind)} · ${data.groups[first.group]}`, statusText, typeText,
                withReads ? `${readsText(reads)} reads${requested ? ` of ${readsText(requested)} requested` : ""}` : null].filter(Boolean).join("\n"),
        },
            h(Handle, { type: "target", position: Position.Left, style: hidden, isConnectable: false }),
            h("div", { className: "ov-row" },
                h("span", { className: "ov-label" }, `${members.length} ${plural.get(first.kind)}`),
                h("button", {
                    type: "button", className: "ov-btn nodrag", title: "Show them one by one",
                    onClick: (ev) => { ev.stopPropagation(); d.toggle(d.unit.groupKey, d.unit.id); },
                }, "+")),
            h("div", { className: "ov-sub" }, data.groups[first.group]),
            h(StatusBars, { counts }),
            h("div", { className: "ov-counts" }, counts.map((c) => `${c.status ? c.status.icon : "–"} ${c.count}`).join("  ")
                + (withReads ? ` · ${readsText(reads)} reads` : "")),
            requested ? h(ReadsBar, { reads, requested }) : null,
            h(Handle, { type: "source", position: Position.Right, style: hidden, isConnectable: false }),
        );
    }

    function HeaderNode({ data: d }) {
        const counts = countStatuses(model, d.members);
        return h("div", { className: "ov-header" },
            h("div", { className: "ov-header-title" }, `${d.label} · ${d.members.length}`),
            counts.some((c) => c.status) ? h(StatusBars, { counts }) : null,
            h("div", { className: "ov-chips" }, counts.filter((c) => c.status).map((c) => {
                const active = d.focus?.type === "status" && d.focus.kind === d.kind && d.focus.status === c.key;
                return h("button", {
                    key: c.key, type: "button", className: `ov-chip nodrag${active ? " ov-active" : ""}`,
                    title: `${c.status.label}: ${c.count} — click to trace them`,
                    onClick: (ev) => { ev.stopPropagation(); d.setFocus(active ? null : { type: "status", kind: d.kind, status: c.key }); },
                }, `${c.status.icon} ${c.count}`);
            })),
        );
    }

    // a pool's edge to its experiment: its lanes as badges where the edge leaves the pool, "1–2" for a run of lanes
    function LanesEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, data }) {
        const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
        const runs = laneRuns(data.lanes);
        return h(React.Fragment, null,
            h(BaseEdge, { path, style }),
            h(EdgeLabelRenderer, null,
                h("div", {
                    className: "ov-lanes nodrag nopan",
                    title: `${data.lanes.length === 1 ? "Lane" : "Lanes"} ${runs.join(", ")}`,
                    style: { transform: `translate(${sourceX + 3}px, ${sourceY}px) translateY(-50%)`, opacity: data.dim ? 0.15 : 1 },
                }, runs.map((run) => h("span", { key: run, className: "ov-lane" }, run)))));
    }

    const nodeTypes = { item: ItemNode, bundle: BundleNode, header: HeaderNode };
    const edgeTypes = { lanes: LanesEdge };
    const membersOf = new Map(data.columns.map((c) => [c.kind, model.nodes.filter((n) => n.kind === c.kind)]));

    function Graph() {
        const flow = useReactFlow();
        const [bundled, setBundled] = React.useState(model.bundled);
        const [focus, setFocus] = React.useState(null);     // pinned: {type: "unit"|"status"|"search", …}
        const [hover, setHover] = React.useState(null);
        const [query, setQuery] = React.useState("");
        const keep = React.useRef(null);                    // keep a toggled node where it was on screen
        // the canvas fills the popup; nodes widen to fill it and the graph is fitted to its width (at most 1:1), top first
        const frame = React.useRef(null);
        const [size, setSize] = React.useState({ width: container.clientWidth, height: container.clientHeight - 34 });
        const nodeWidth = nodeWidthFor(size.width, data.columns.length);
        const view = React.useMemo(() => layout(model, bundled, nodeWidth), [bundled, nodeWidth]);
        const labelSizes = React.useMemo(() => new Map(model.nodes.map((n) => [n.id, labelSize(n.label, n.aside, nodeWidth)])), [nodeWidth]);
        React.useEffect(() => {
            const observer = new ResizeObserver(([entry]) => {
                const { width, height } = entry.contentRect;
                if (width > 0 && height > 0) setSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
            });
            observer.observe(frame.current);
            return () => observer.disconnect();
        }, []);
        const scale = Math.min(1, (size.width - 2) / view.bounds.width);
        const tall = view.bounds.height * scale > size.height;
        const fitted = {
            x: Math.max(0, (size.width - view.bounds.width * scale) / 2) - view.bounds.x * scale,
            y: -view.bounds.y * scale, zoom: scale,
        };

        const toggle = React.useCallback((groupKey, unitId) => {
            const p = view.pos.get(unitId);
            const vp = flow.getViewport();
            keep.current = p ? { groupKey, screenY: p.y * vp.zoom + vp.y } : null;
            setBundled((prev) => {
                const next = new Set(prev);
                next.has(groupKey) ? next.delete(groupKey) : next.add(groupKey);
                return next;
            });
        }, [view]);

        // refit when the graph or the popup changes size; after a bundle is toggled, keep its node where
        // it was on screen (and the zoom as it was)
        const first = React.useRef(true);
        React.useLayoutEffect(() => {
            if (first.current) {
                first.current = false;  // React Flow starts at defaultViewport
                return;
            }
            const kept = keep.current;
            keep.current = null;
            if (kept) {
                const unit = [...view.units.values()].find((u) => u.groupKey === kept.groupKey);
                const p = unit && view.pos.get(unit.id);
                const vp = flow.getViewport();
                if (p) {
                    flow.setViewport({ ...vp, y: kept.screenY - p.y * vp.zoom });
                    return;
                }
            }
            flow.setViewport(fitted);
        }, [view, size]);

        // what is traced: the hovered node, else the pinned focus
        const traced = React.useMemo(() => {
            const active = hover ? { type: "unit", id: hover } : focus;
            if (!active) return null;
            const seeds = new Set();
            for (const u of view.units.values()) {
                if (active.type === "unit" && u.id === active.id) seeds.add(u.id);
                if (active.type === "status" && u.kind === active.kind && u.members.some((n) => String(n.status) === active.status)) seeds.add(u.id);
                if (active.type === "search" && u.members.some((n) => n.label.toLowerCase().includes(active.q))) seeds.add(u.id);
            }
            return { seeds, ...trace(view, seeds) };
        }, [view, hover, focus]);

        const nodes = React.useMemo(() => {
            const out = data.columns.map((c, i) => ({
                id: `header:${c.kind}`, type: "header", position: { x: i * (nodeWidth + COLUMN_GAP), y: -model.headerHeight - 4 },
                data: { kind: c.kind, label: c.label, members: membersOf.get(c.kind), focus, setFocus },
                draggable: false, selectable: false, focusable: false,
            }));
            for (const u of view.units.values()) {
                const p = view.pos.get(u.id);
                out.push({
                    id: u.id, type: u.bundle ? "bundle" : "item", position: { x: p.x, y: p.y },
                    className: traced && !traced.units.has(u.id) ? "ov-dim" : "",
                    data: {
                        unit: u, toggle, labelSize: u.bundle ? null : labelSizes.get(u.members[0].id), seed: !!traced && traced.seeds.has(u.id) && (focus?.type !== "unit" || hover),
                        pinned: focus?.type === "unit" && focus.id === u.id,
                    },
                    draggable: false, selectable: false, focusable: false,
                });
            }
            return out;
        }, [view, labelSizes, traced, focus, hover]);

        const edges = React.useMemo(() => [...view.edges.values()].map((e) => {
            const on = traced?.edges.has(e.id);
            const label = e.labels.size === 1 && e.count === 1 ? [...e.labels][0] : e.count > 1 ? `${e.count}` : undefined;
            const lanes = [...e.lanes].sort((a, b) => a - b);
            return {
                id: e.id, source: e.source, target: e.target,
                ...(lanes.length ? { type: "lanes", data: { lanes, dim: !!traced && !on } } : { label }),
                selectable: false, focusable: false,
                style: {
                    stroke: on ? "var(--bs-primary, #0d6efd)" : "var(--bs-secondary-color, #6c757d)",
                    strokeWidth: Math.min(1 + Math.log2(e.count), 7) + (on ? 0.5 : 0),
                    opacity: traced ? (on ? 0.9 : 0.08) : 0.35,
                },
                labelBgPadding: [3, 1], labelBgBorderRadius: 3,
                zIndex: on ? 1 : 0,
            };
        }), [view, traced]);

        const search = (q) => {
            setQuery(q);
            const trimmed = q.trim().toLowerCase();
            setFocus(trimmed ? { type: "search", q: trimmed } : null);
        };
        const canBundle = model.bundleable.size > 0;
        const allBundled = canBundle && [...model.bundleable].every((k) => bundled.has(k));
        const nothingBundled = [...model.bundleable].every((k) => !bundled.has(k));
        const matches = focus?.type === "search" && traced ? traced.seeds.size : null;

        return h("div", { className: "ov-wrap", style: { "--ov-node-width": `${nodeWidth}px` } },
            h("div", { className: "ov-bar" },
                h("input", { type: "search", placeholder: "Find by name…", value: query, onChange: (ev) => search(ev.target.value), "aria-label": "Find by name" }),
                matches !== null ? h("span", null, matches ? `${matches} found` : "nothing found") : null,
                canBundle && !nothingBundled ? h("button", { type: "button", onClick: () => setBundled(new Set()) }, "Expand all") : null,
                canBundle && !allBundled ? h("button", { type: "button", onClick: () => setBundled(new Set(model.bundleable)) }, "Bundle all") : null,
                h("button", { type: "button", title: "Zoom out", onClick: () => flow.zoomOut() }, "−"),
                h("button", { type: "button", title: "Zoom in", onClick: () => flow.zoomIn() }, "+"),
                h("button", { type: "button", title: "Fit the width again", onClick: () => flow.setViewport(fitted, { duration: 200 }) }, "Fit"),
                h("span", { className: "ov-hint" }, `hover a node to trace it · click to keep the trace · click a status to trace all in it · scroll to pan, ${ZOOM_KEY}+scroll to zoom`),
            ),
            h("div", { className: "ov-flow", ref: frame },
                h(ReactFlow, {
                    nodes, edges, nodeTypes, edgeTypes, defaultViewport: fitted,
                    nodesConnectable: false, nodesDraggable: false, elementsSelectable: false,
                    minZoom: 0.1, maxZoom: 1.5, onlyRenderVisibleElements: true,
                    onNodeMouseEnter: (_, node) => node.type !== "header" && setHover(node.id),
                    onNodeMouseLeave: () => setHover(null),
                    onNodeClick: (_, node) => {
                        if (node.type === "header") return;
                        setHover(null);
                        setFocus((prev) => (prev?.type === "unit" && prev.id === node.id ? null : { type: "unit", id: node.id }));
                    },
                    onPaneClick: () => setFocus(null),
                    panOnDrag: true, panOnScroll: true, zoomOnScroll: false, zoomOnPinch: true, zoomOnDoubleClick: false,
                    translateExtent: [[view.bounds.x - 200, view.bounds.y - 50], [view.bounds.x + view.bounds.width + 200, view.bounds.y + view.bounds.height + 300]],
                    proOptions: { hideAttribution: true },
                },
                tall ? h(MiniMap, {
                    pannable: true, zoomable: false, ariaLabel: "Overview map", style: { width: 120, height: 90, opacity: 0.85 },
                    nodeColor: (node) => {
                        if (node.type !== "item") return "#adb5bd";
                        const status = model.status(node.data.unit.members[0]);
                        return status ? TONES[status.tone] : NO_STATUS;
                    },
                }) : null),
            ),
        );
    }

    ReactDOMClient.createRoot(container).render(h(ReactFlowProvider, null, h(Graph)));
}

// Mounts the graphs of a popup (overview-graph.jinja2), each the first time it is shown: the first view's
// data and the modules load while the popup fades in, the graph renders once it has its full size. A
// switch in the header (several views) shows another view, loading it then.
export function mountOnOpen(modal) {
    const views = new Map([...modal.querySelectorAll(".overview-graph")].map((container) => [container.dataset.view, { container, loading: null, shown: false }]));
    const failed = (container) => (err) => {
        console.warn("Overview not available:", err);
        container.innerHTML = '<div class="ov-empty">The overview could not be loaded.</div>';
    };
    const load = (view) => {
        view.loading ??= Promise.all([loadModules(), fetchData(view.container.dataset.url)]);
        view.loading.catch(() => {});  // reported once shown
    };
    const show = (view) => {
        if (view.shown) return;
        view.shown = true;
        load(view);
        view.loading.then(([modules, data]) => render(view.container, modules, data)).catch(failed(view.container));
    };
    const first = views.values().next().value;
    modal.addEventListener("show.bs.modal", () => load(first), { once: true });
    modal.addEventListener("shown.bs.modal", () => show(first), { once: true });
    modal.querySelectorAll(`input[name="${modal.id}-view"]`).forEach((input) => input.addEventListener("change", () => {
        for (const [key, view] of views) view.container.classList.toggle("d-none", key !== input.value);
        show(views.get(input.value));
    }));
}
