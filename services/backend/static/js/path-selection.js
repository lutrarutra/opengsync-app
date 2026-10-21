// Paths picked in the insider file browser for Associate/Share, kept in localStorage so they survive
// reloads and stay in sync across tabs. Loaded by files_page.html (insider browser) and by the Data tab
// picker (data-picker.html), whose panel has data-persist="false" and a form that submits the changes: its
// data-initial-paths (the linked ones) start ticked, and the form posts what was ticked (add-N) and unticked (remove-N).
(function() {
    const panel = document.getElementById('path-selection-panel');
    if (!panel) return;

    const STORAGE_KEY = panel.dataset.persist === 'false' ? null : 'opengsync:path-selection';

    const MAX_PATHS = parseInt(panel.dataset.maxPaths, 10);
    // adding data paths: a share root (<root> itself) can't be picked, only what is inside it
    const ALLOW_ROOTS = panel.dataset.allowRoots !== 'false';
    const INITIAL = new Set(JSON.parse(panel.dataset.initialPaths || '[]'));
    const OWNER = panel.dataset.ownerLabel || '';
    const list = panel.querySelector('.path-selection-list');
    const count = panel.querySelector('.path-selection-count');
    let selected = new Set(STORAGE_KEY ? load() : INITIAL);

    function additions() {
        return Array.from(selected).filter(function(path) { return !INITIAL.has(path); }).sort();
    }

    function removals() {
        return Array.from(INITIAL).filter(function(path) { return !selected.has(path); }).sort();
    }

    function load() {
        if (!STORAGE_KEY) return [];
        try {
            const paths = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(paths) ? paths.filter(function(path) { return typeof path === 'string'; }) : [];
        } catch (e) {
            return [];
        }
    }

    // Without storage (private window, blocked site data) the selection still works, it just isn't kept.
    function save() {
        if (!STORAGE_KEY) return;
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
            const isSelected = selected.has(row.dataset.path);
            row.classList.toggle('is-selected', isSelected);
            const checkbox = row.querySelector('.browser-entry-pick');
            if (checkbox) checkbox.checked = isSelected;
        });
    }

    // the Data tab picker posts its changes as `add-0`, `add-1`, ... and `remove-0`, ... fields
    function fillForm() {
        const form = panel.querySelector('.path-selection-form');
        if (!form) return;
        const added = additions();
        const removed = removals();
        form.querySelector('[type="submit"]').disabled = added.length + removed.length === 0;
        form.querySelectorAll('input.path-selection-field').forEach(function(input) { input.remove(); });
        [['add-', added], ['remove-', removed]].forEach(function(field) {
            field[1].forEach(function(path, index) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.className = 'path-selection-field';
                input.name = field[0] + index;
                input.value = path;
                form.appendChild(input);
            });
        });
    }

    function renderPanel() {
        const paths = Array.from(new Set([...selected, ...INITIAL])).sort();
        panel.hidden = paths.length === 0;
        count.textContent = selected.size === 1 ? '1 path selected' : selected.size + ' paths selected';
        if (INITIAL.size) {
            const changes = [];
            const added = additions().length;
            const removed = removals().length;
            if (added) changes.push(added + ' to add');
            if (removed) changes.push(removed + ' to remove');
            count.textContent += changes.length ? ' · ' + changes.join(', ') : '';
        }
        list.replaceChildren(...paths.map(function(path) {
            // in the picker: linked (ticked), new (ticked, not linked yet) or to be unlinked (unticked)
            const isLinked = INITIAL.has(path);
            const isRemoved = isLinked && !selected.has(path);
            const item = document.createElement('li');
            item.className = 'path-selection-item' + (isRemoved ? ' is-removed' : '') + (INITIAL.size && !isLinked ? ' is-new' : '');

            // rtl + <bdi>: a long path is truncated at its start, keeping the file name visible
            const label = document.createElement('span');
            label.className = 'path-selection-path';
            label.title = path + (isRemoved ? ' (will be removed from the ' + OWNER + ')' : isLinked ? ' (in the ' + OWNER + ')' : '');
            const text = document.createElement('bdi');
            text.textContent = path;
            label.appendChild(text);

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'path-selection-icon-button';
            button.dataset.path = path;
            if (isRemoved) {
                button.title = 'Keep in the ' + OWNER;
                button.setAttribute('aria-label', 'Keep ' + path + ' in the ' + OWNER);
                button.innerHTML = '<i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>';
            } else {
                button.title = isLinked ? 'Remove from the ' + OWNER : 'Remove from selection';
                button.setAttribute('aria-label', 'Remove ' + path + (isLinked ? ' from the ' + OWNER : ' from selection'));
                button.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
            }

            item.append(label, button);
            return item;
        }));
    }

    function update() {
        save();
        renderPanel();
        highlightRows();
        fillForm();
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
        // unsaved picks or unticks (the picker asks before closing)
        changed: function() { return additions().length + removals().length > 0; },
        toggle: function(path) {
            if (selected.has(path)) {
                selected.delete(path);
            } else if (INITIAL.has(path)) {
                selected.add(path);  // kept after all
            } else if (!ALLOW_ROOTS && !path.includes('/')) {
                swal_message('A whole share folder can\'t be added, only files and folders inside it', 'warning');
                return;
            } else if (additions().length >= MAX_PATHS) {
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
        // the picker goes back to the linked paths
        clear: function() {
            selected = new Set(STORAGE_KEY ? [] : INITIAL);
            update();
        },
    };

    list.addEventListener('click', function(event) {
        const button = event.target.closest('button[data-path]');
        if (button) window.pathSelection.toggle(button.dataset.path);
    });

    if (INITIAL.size) panel.querySelector('.path-selection-clear').title = 'Undo changes';
    panel.querySelector('.path-selection-clear').addEventListener('click', function() {
        window.pathSelection.clear();
    });

    panel.querySelector('.path-selection-collapse').addEventListener('click', function() {
        const collapsed = panel.classList.toggle('is-collapsed');
        this.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });

    const associateButton = panel.querySelector('.path-selection-associate');
    if (associateButton) {
        associateButton.addEventListener('click', function() {
            openForm(panel.dataset.associateUrl);
        });
    }

    const shareButton = panel.querySelector('.path-selection-share');
    if (shareButton) {
        shareButton.addEventListener('click', function() {
            openForm(panel.dataset.shareUrl, { from_selection: 'true' });
        });
    }

    // the picker: unlinking needs a confirmation
    const form = panel.querySelector('.path-selection-form');
    if (form) {
        form.addEventListener('htmx:confirm', function(event) {
            const removed = removals();
            if (!removed.length) return;
            event.preventDefault();
            Swal.fire({
                title: 'Remove ' + (removed.length === 1 ? '1 path' : removed.length + ' paths') + ' from the ' + OWNER + '?',
                text: 'The files stay on disk.',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Save',
            }).then(function(result) {
                if (result.isConfirmed) event.detail.issueRequest(true);
            });
        });
    }

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
        if (!STORAGE_KEY || (event.key !== STORAGE_KEY && event.key !== null)) return;
        selected = new Set(load());
        renderPanel();
        highlightRows();
    });

    renderPanel();
    highlightRows();
    fillForm();
})();
