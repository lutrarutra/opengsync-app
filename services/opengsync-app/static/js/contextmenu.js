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
        Swal.fire({
            position: 'top',
            icon: 'success',
            title: `Copied to clipboard`,
            showConfirmButton: false,
            timer: 1000,
            toast: true
        });
    } else {
        Swal.fire({
            position: 'top',
            icon: 'error',
            title: `Failed to copy to clipboard`,
            showConfirmButton: false,
            timer: 1000,
            toast: true
        });
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
        e.preventDefault();
        
        const $element = $(this);
        const menuData = $element.data('context-menu');
        
        if (!menuData?.actions?.length) return;
        
        const menuItems = menuData.actions.map(action => createMenuItem(action, $element));
        
        showContextMenu(e.pageX, e.pageY, menuItems);
    });
}

function createMenuItem(action, $contextElement) {
    const li = $('<li>');
    const link = $('<button>', {
        class: 'dropdown-item',
        text: action.label || formatActionLabel(action),
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

function hx_request(url, title, text, icon, swap, target, confirm, type) {

    function send_request() {
        htmx.ajax(type, url, {
            target: target,
            swap: swap,
        }).then(() => {
            Swal.fire({
                position: 'top',
                icon: 'success',
                title: 'Request Successful!',
                showConfirmButton: false,
                timer: 1000,
                toast: true
            });
        }).catch(() => {
            Swal.fire({
                position: 'top',
                icon: 'error',
                title: 'Request Failed!',
                showConfirmButton: false,
                timer: 1000,
                toast: true
            });
        });
    }

    if (confirm) {
        Swal.fire({
            title: title,
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
    const handlers = {
        copy: (action) => {
            copy_to_clipboard(action.value);
        },
        hxdelete: (action) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title,
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm || true,
                "DELETE"
            );
        },
        hxpost: (action) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title,
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm || true,
                "POST"
            );
        },
        hxget: (action) => {
            const config = action.config;
            hx_request(
                config.url,
                config.title,
                config.text || "Do you want to continue?",
                config.icon || "question",
                config.swap || "outerHTML",
                config.target,
                config.confirm || true,
                "GET"
            );
        }
    };
    
    const handler = handlers[action.type];
    if (handler) {
        handler(action, $contextElement);
    } else {
        console.warn(`No handler for action type: ${action.type}`);
    }
}

function showContextMenu(x, y, menuItems) {
    const $container = $("#context-menu-container");
    const $background = $("#right-click-bg");
    
    $container.empty().append(menuItems)
        .css({ 
            display: "block",
            left: x + 8, 
            top: y + 8
        });
    
    $background.css({ display: "block" });
}

function hideContextMenu() {
    $("#context-menu-container, #right-click-bg").hide();
}

// Close menu when clicking elsewhere
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