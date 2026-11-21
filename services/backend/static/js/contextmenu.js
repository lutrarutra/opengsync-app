function swal_message(title, icon, text=null, timer=2000) {
    Swal.fire({
        position: 'top',
        icon: icon,
        titleText: title,
        text: text,
        showConfirmButton: false,
        timer: timer,
        toast: true
    });
};

function copy_value_to_clipboard(uuid) {
    const s = $("#" + uuid + " input").first().val();

    copy_to_clipboard(s);

    $(".copied-icon").css({
        display: "none"
    });
    $(".not-copied-icon").css({
        display: "inline-block"
    });
    $(`#${uuid} a .not-copied-icon`).css({
        display: "none"
    });
    $(`#${uuid} a .copied-icon`).css({
        display: "inline-block"
    });
};

function unsecuredCopyToClipboard(text) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    var successful = true;
    try {
        document.execCommand('copy');
    } catch (err) {
        console.error('Unable to copy to clipboard', err);
        successful = false;
    }
    document.body.removeChild(textArea);
    return successful;
}

function copy_to_clipboard(text) {
    var successful = true;
    try {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
        } else {
            successful = unsecuredCopyToClipboard(text);
        }
    }
    catch (err) {
        console.error('Unable to copy to clipboard', err);
        successful = false;
    }
    if (successful) {
        swal_message('Copied to clipboard', 'success');
    } else {
        swal_message('Copy to clipboard failed', 'error');
    }
}

function copy_text(text) {
    if (text) {
        copy_to_clipboard(text);
    }
    $("#context-menu-container").css({
        display: "none"
    }).empty();
    $("#right-click-bg").css({
        display: "none"
    });
}

function init_context_menu_callbacks() {
    $(document).off("contextmenu", ".cm-callback").on("contextmenu", ".cm-callback", function(e) {
        // if shift is held down, do not show context menu
        if (e.shiftKey) {
            return;
        }
        e.preventDefault();
        
        const $element = $(this);
        const menuData = $element.data('context-menu');
        
        if (!menuData?.actions?.length) return;
        
        const actions = [...menuData.actions];
        // cells of a table body can also copy their whole column (as shown on this page)
        if ($element.closest(".otable tbody").length && $element.is("td, th")) {
            actions.push({ type: "copy_column", label: "Copy column" });
        }
        const menuItems = actions.map(action => createMenuItem(action, $element));

        showContextMenu(e.pageX, e.pageY, menuItems);
    });
}

// The ⋯ button of a table row opens the same kind of menu on a left click (see row_menu in contextmenu.jinja2)
function open_row_menu(button) {
    const $button = $(button);
    const menuData = $button.data('context-menu');
    if (!menuData?.actions?.length) return;
    const rect = button.getBoundingClientRect();
    const menuItems = menuData.actions.map(action => createMenuItem(action, $button));
    showContextMenu(rect.right + window.scrollX - 8, rect.bottom + window.scrollY - 8, menuItems, { alignRight: true });
    $("#context-menu-container .dropdown-item:not(.disabled)").first().trigger("focus");
}

$(document).on("click", ".row-menu-btn", function(e) {
    e.preventDefault();
    e.stopPropagation();
    window._rowMenuOpener = this;
    open_row_menu(this);
});

// Keyboard in the open menu: Escape closes it (focus back to the ⋯ button), arrows move between items.
// Caught on window in the capture phase: Bootstrap's own dropdown key handler (a capturing listener on
// document) expects a toggle button this menu has not and would throw.
window.addEventListener("keydown", (e) => {
    const menu = document.getElementById("context-menu-container");
    if (!menu || !menu.contains(e.target)) return;
    if (!["Escape", "ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") {
        hideContextMenu();
        if (window._rowMenuOpener && document.body.contains(window._rowMenuOpener)) window._rowMenuOpener.focus();
        return;
    }
    const items = Array.from(menu.querySelectorAll(".dropdown-item:not(.disabled)"));
    if (!items.length) return;
    const index = items.indexOf(document.activeElement);
    const next = {
        ArrowDown: (index + 1) % items.length,
        ArrowUp: (index - 1 + items.length) % items.length,
        Home: 0,
        End: items.length - 1,
    }[e.key];
    items[next].focus();
}, true);

// Shift+F10 / the context-menu key: open the menu of the focused ⋯ button or right-click cell
$(document).on("keydown", function(e) {
    if (!((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu")) return;
    const focused = document.activeElement;
    if (!focused) return;
    if (focused.classList.contains("row-menu-btn")) {
        e.preventDefault();
        open_row_menu(focused);
        return;
    }
    const cell = focused.closest(".cm-callback");
    if (cell) {
        e.preventDefault();
        const rect = cell.getBoundingClientRect();
        $(cell).trigger($.Event("contextmenu", { pageX: rect.left + window.scrollX, pageY: rect.bottom + window.scrollY }));
    }
});

function formatActionLabel(action) {
    const type = (action.type || "").replace(/^hx/, "").replace(/_/g, " ");
    return type.charAt(0).toUpperCase() + type.slice(1);
}

function copy_table_column(cell) {
    const tbody = cell.closest("tbody");
    if (!tbody) return;
    const index = cell.cellIndex;
    const values = Array.from(tbody.rows)
        .map(row => row.cells[index] ? row.cells[index].innerText.trim() : "")
        .filter(value => value.length > 0);
    if (values.length) copy_to_clipboard(values.join("\n"));
}

function createMenuItem(action, $contextElement) {
    const li = $('<li>');
    let label = action.label || formatActionLabel(action);
    // Menus are built on every right-click, so the label follows the current selection
    if (action.type === 'select' && window.pathSelection) {
        label = window.pathSelection.has(action.config.path) ? 'Deselect' : 'Select';
    }
    const link = $('<button>', {
        class: 'dropdown-item' + (action.active ? ' active' : ''),
        text: label,
    });

    if (action.disabled) {
        link.addClass('disabled');
    } else {
        link.on('click', (e) => {
            e.preventDefault();
            handleContextMenuAction(action, $contextElement);
            hideContextMenu();
        });
    }
    
    
    return li.append(link);
}

function hx_request(url, title, text, icon, swap, target, confirm, type, sourceElement) {
    function send_request() {
        const opts = { target: target, swap: swap };
        if (sourceElement) {
            opts.source = sourceElement;
        }
        htmx.ajax(type, url, opts);
    }

    if (confirm) {
        Swal.fire({
            titleText: title,
            showDenyButton: true,
            text: text,
            confirmButtonText: 'Yes',
            icon: icon,
            denyButtonText: 'No'
        }).then(function(result) {
            if (result.isConfirmed) {
                send_request();
            }
        });
    } else {
        send_request();
    }
}


function handleContextMenuAction(action, $contextElement) {
    var show_modal = action.show_modal;
    const handlers = {
        copy: (action) => {
            copy_to_clipboard(action.value);
        },
        copy_column: (action, $contextElement) => {
            const cell = $contextElement ? $contextElement.closest("td, th")[0] : null;
            if (cell) copy_table_column(cell);
        },
        select: (action) => {
            window.pathSelection?.toggle(action.config.path);
        },
        mailto: (action) => {
            const config = action.config;
            window.location.href = `mailto:${encodeURIComponent(config.recipient || '')}?subject=${encodeURIComponent(config.subject || '')}`;
        },
        hxdelete: (action, $contextElement) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title || "",
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm ?? true,
                "DELETE",
                $contextElement ? $contextElement[0] : undefined
            );
        },
        hxpost: (action, $contextElement) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title || "",
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm ?? true,
                "POST",
                $contextElement ? $contextElement[0] : undefined
            );
        },
        hxget: (action, $contextElement) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title || "",
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm ?? true,
                "GET",
                $contextElement ? $contextElement[0] : undefined
            );
        }
    };

    if (show_modal) {
        $(show_modal).modal('show');
    }
    
    const handler = handlers[action.type];
    if (handler) {
        handler(action, $contextElement);
    } else {
        console.warn(`No handler for action type: ${action.type}`);
    }
}

function showContextMenu(x, y, menuItems, options = {}) {
    const $container = $("#context-menu-container");
    const $background = $("#right-click-bg");

    // the overlay holds the menu: show it first, so the menu can be measured
    $background.css({ display: "block" });
    $container.empty().append(menuItems)
        .css({
            display: "block",
            left: x + 8,
            top: y + 8
        });

    // keep the menu inside the viewport (and right-aligned to a ⋯ button)
    const menu = $container[0];
    const width = menu.offsetWidth, height = menu.offsetHeight;
    let left = options.alignRight ? x + 8 - width : x + 8;
    let top = y + 8;
    const maxLeft = window.scrollX + document.documentElement.clientWidth - width - 8;
    const maxTop = window.scrollY + document.documentElement.clientHeight - height - 8;
    left = Math.max(window.scrollX + 8, Math.min(left, maxLeft));
    if (top > maxTop) top = Math.max(window.scrollY + 8, y - height - 8);
    $container.css({ left: left, top: top });

    $background.css({ display: "block" });
}

function hideContextMenu() {
    $("#context-menu-container, #right-click-bg").hide();
}

$(document).on('click', '#right-click-bg, body', function(e) {
    if ($(e.target).is('#right-click-bg') || !$(e.target).closest('#context-menu-container').length) {
        hideContextMenu();
    }
});

document.addEventListener("htmx:afterRequest", () => {
    init_context_menu_callbacks();
});
$(document).ready(function() {
    init_context_menu_callbacks();
});