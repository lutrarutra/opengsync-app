// Paths picked in the insider file browser for Associate/Share, kept in localStorage so they survive
// reloads and stay in sync across tabs. Only files_page.html loads this, and only for the insider browser.
(function() {
    const STORAGE_KEY = 'opengsync:path-selection';

    const panel = document.getElementById('path-selection-panel');
    if (!panel) return;

    const MAX_PATHS = parseInt(panel.dataset.maxPaths, 10);
    const list = panel.querySelector('.path-selection-list');
    const count = panel.querySelector('.path-selection-count');
    let selected = new Set(load());

    function load() {
        try {
            const paths = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(paths) ? paths.filter(function(path) { return typeof path === 'string'; }) : [];
        } catch (e) {
            return [];
        }
    }

    // Without storage (private window, blocked site data) the selection still works, it just isn't kept.
    function save() {
        try {
            if (selected.size) {
                window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(selected)));
            } else {
                window.localStorage.removeItem(STORAGE_KEY);
            }
        } catch (e) {}
    }

    function highlightRows() {
        document.querySelectorAll('.browser-entry-row[data-path]').forEach(function(row) {
            row.classList.toggle('is-selected', selected.has(row.dataset.path));
        });
    }

    function renderPanel() {
        const paths = Array.from(selected).sort();
        panel.hidden = paths.length === 0;
        count.textContent = paths.length === 1 ? '1 path selected' : paths.length + ' paths selected';
        list.replaceChildren(...paths.map(function(path) {
            const item = document.createElement('li');
            item.className = 'path-selection-item';

            // rtl + <bdi>: a long path is truncated at its start, keeping the file name visible
            const label = document.createElement('span');
            label.className = 'path-selection-path';
            label.title = path;
            const text = document.createElement('bdi');
            text.textContent = path;
            label.appendChild(text);

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'path-selection-icon-button';
            remove.dataset.path = path;
            remove.title = 'Remove from selection';
            remove.setAttribute('aria-label', 'Remove ' + path + ' from selection');
            remove.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';

            item.append(label, remove);
            return item;
        }));
    }

    function update() {
        save();
        renderPanel();
        highlightRows();
    }

    function openForm(url, extraParams) {
        const params = new URLSearchParams(extraParams || {});
        Array.from(selected).sort().forEach(function(path) { params.append('path', path); });
        $('#xl-modal').modal('show');
        htmx.ajax('GET', url + (url.includes('?') ? '&' : '?') + params, {
            target: '#xl-modal-content',
            swap: 'innerHTML',
        });
    }

    window.pathSelection = {
        has: function(path) { return selected.has(path); },
        list: function() { return Array.from(selected).sort(); },
        toggle: function(path) {
            if (selected.has(path)) {
                selected.delete(path);
            } else if (selected.size >= MAX_PATHS) {
                swal_message('At most ' + MAX_PATHS + ' paths can be selected', 'warning');
                return;
            } else {
                selected.add(path);
            }
            update();
        },
        remove: function(path) {
            selected.delete(path);
            update();
        },
        clear: function() {
            selected.clear();
            update();
        },
    };

    list.addEventListener('click', function(event) {
        const button = event.target.closest('button[data-path]');
        if (button) window.pathSelection.remove(button.dataset.path);
    });

    panel.querySelector('.path-selection-clear').addEventListener('click', function() {
        window.pathSelection.clear();
    });

    panel.querySelector('.path-selection-collapse').addEventListener('click', function() {
        const collapsed = panel.classList.toggle('is-collapsed');
        this.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });

    panel.querySelector('.path-selection-associate').addEventListener('click', function() {
        openForm(panel.dataset.associateUrl);
    });

    panel.querySelector('.path-selection-share').addEventListener('click', function() {
        openForm(panel.dataset.shareUrl, { from_selection: 'true' });
    });

    // Ctrl/Cmd+click toggles a row instead of opening it. Capture phase, so the folder toggle,
    // its htmx request and file links never see the click.
    const root = document.getElementById('file-browser-root');
    if (root) {
        root.addEventListener('click', function(event) {
            if (!(event.ctrlKey || event.metaKey)) return;
            const row = event.target.closest('.browser-entry-row[data-path]');
            if (!row) return;
            event.preventDefault();
            event.stopPropagation();
            window.pathSelection.toggle(row.dataset.path);
        }, true);
    }

    // Folders load lazily, pages load on scroll and sorting re-renders the tree.
    document.body.addEventListener('htmx:afterSettle', highlightRows);

    // Another tab changed the selection
    window.addEventListener('storage', function(event) {
        if (event.key !== STORAGE_KEY && event.key !== null) return;
        selected = new Set(load());
        renderPanel();
        highlightRows();
    });

    renderPanel();
    highlightRows();
})();
