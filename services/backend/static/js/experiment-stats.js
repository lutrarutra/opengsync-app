// Experiment stats tab (templates/components/experiment-stats.html): level switch, pool expand,
// QC column toggle, client-side sort and filter. The fragment calls initExperimentStats() after each swap.
(function () {
    const LEVEL_KEY = "expStats.level";
    const QC_KEY = "expStats.qc";

    function load(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function store(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ }
    }

    function setLevel(root, level) {
        root.querySelectorAll("[data-level-pane]").forEach(pane => {
            pane.hidden = pane.dataset.levelPane !== level;
        });
        root.querySelectorAll("[data-level-only]").forEach(el => {
            el.hidden = el.dataset.levelOnly !== level;
        });
    }

    function setExpanded(unit, expanded) {
        unit.classList.toggle("is-expanded", expanded);
        const button = unit.querySelector("[data-expand]");
        if (button) button.setAttribute("aria-expanded", String(expanded));
    }

    // same icons as the server-side tables (components/table_col.jinja2)
    function setSortIcon(th, dir) {
        const icon = th.querySelector(".sort-btn i");
        if (!icon) return;
        icon.className = dir === null ? "bi bi-filter" : dir === "asc" ? "bi bi-sort-down" : "bi bi-sort-down-alt";
    }

    function sortTable(table, th) {
        const key = th.dataset.sortKey;
        const numeric = th.dataset.sortType === "num";
        const dir = th.dataset.sortDir === "desc" ? "asc" : "desc";
        table.querySelectorAll("th[data-sort-key]").forEach(h => {
            delete h.dataset.sortDir;
            h.removeAttribute("aria-sort");
            setSortIcon(h, null);
        });
        th.dataset.sortDir = dir;
        th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
        setSortIcon(th, dir);

        // pools table: one <tbody> per pool (with its library rows); libraries table: one <tr> per library
        const units = Array.from(table.querySelectorAll("[data-sort-unit]"));
        const parent = units.length ? units[0].parentNode : null;
        if (!parent) return;
        const value = unit => {
            const raw = unit.dataset[key] ?? "";
            if (!numeric) return raw;
            const n = parseFloat(raw);
            return isNaN(n) ? null : n;
        };
        const sign = dir === "asc" ? 1 : -1;
        units.sort((a, b) => {
            const pinA = a.hasAttribute("data-pin-last"), pinB = b.hasAttribute("data-pin-last");
            if (pinA !== pinB) return pinA ? 1 : -1;
            const va = value(a), vb = value(b);
            if (va === vb) return 0;
            if (va === null) return 1;  // empty values last in both directions
            if (vb === null) return -1;
            return (numeric ? va - vb : va.localeCompare(vb)) * sign;
        });
        units.forEach(unit => parent.appendChild(unit));
    }

    function applyFilter(root, query) {
        const q = query.trim().toLowerCase();
        root.querySelectorAll("[data-sort-unit]").forEach(unit => {
            const children = unit.querySelectorAll(".es-child-row");
            if (!q) {
                unit.hidden = false;
                children.forEach(row => row.classList.remove("is-match"));
                return;
            }
            const match = (unit.dataset.filter || "").includes(q);
            unit.hidden = !match;
            // a pool that matches only through its libraries shows just those libraries
            const ownMatch = unit.tagName === "TBODY" && unit.querySelector(".es-parent-row a")?.textContent.toLowerCase().includes(q);
            children.forEach(row => row.classList.toggle("is-match", !ownMatch && (row.dataset.filter || "").includes(q)));
        });
    }

    window.initExperimentStats = function (root) {
        if (!root || root.dataset.initialized) return;
        root.dataset.initialized = "1";
        if (typeof init_tooltips === "function") init_tooltips(root);

        const radios = root.querySelectorAll("input.btn-check[value]");
        const saved = load(LEVEL_KEY);
        radios.forEach(radio => {
            if (saved && radio.value === saved) radio.checked = true;
            radio.addEventListener("change", () => {
                if (!radio.checked) return;
                setLevel(root, radio.value);
                store(LEVEL_KEY, radio.value);
            });
        });
        const checked = root.querySelector("input.btn-check:checked");
        if (checked) setLevel(root, checked.value);

        const qcToggle = root.querySelector("[data-qc-toggle]");
        const qcTable = root.querySelector("[data-qc-table]");
        if (qcToggle && qcTable) {
            qcToggle.checked = load(QC_KEY) === "1";
            qcTable.classList.toggle("show-qc", qcToggle.checked);
            qcToggle.addEventListener("change", () => {
                qcTable.classList.toggle("show-qc", qcToggle.checked);
                store(QC_KEY, qcToggle.checked ? "1" : "0");
            });
        }

        root.querySelectorAll("[data-expand]").forEach(button => {
            button.addEventListener("click", () => {
                const unit = button.closest("[data-sort-unit]");
                setExpanded(unit, !unit.classList.contains("is-expanded"));
            });
        });

        root.querySelectorAll("table[data-sortable]").forEach(table => {
            table.querySelectorAll("th[data-sort-key]").forEach(th => {
                const button = th.querySelector(".sort-btn");
                if (!button) return;
                button.addEventListener("click", () => sortTable(table, th));
                button.addEventListener("keydown", e => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortTable(table, th); }
                });
            });
        });

        const filter = root.querySelector("[data-filter-input]");
        if (filter) filter.addEventListener("input", () => applyFilter(root, filter.value));
    };
})();
