function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function deleteCookie(name) {
    document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
}

// Toast messages interpolate user-controlled names (files, samples, ...): always render them as text, never as HTML.
function flashToastContent(text) {
    const content = document.createElement('div');
    content.style.cssText = 'display: flex; justify-content: center; align-items: center; height: 100%; padding: 0; font-weight: 600;';
    content.textContent = text;
    return content;
}

function showFlashToast(msg) {
    Swal.fire({
        position: 'top',
        icon: msg.category || 'success',
        html: flashToastContent(msg.message),
        showConfirmButton: false,
        timer: msg.category === 'error' || msg.category === 'warning' ? null : 1500,
        toast: true,
        showCloseButton: true
    });
}

function checkFlashCookie() {
    const raw = getCookie('flash_message');
    if (raw) {
        let msg = null;
        try {
            msg = JSON.parse(decodeURIComponent(raw));
        } catch (e) {
            try {
                msg = JSON.parse(raw);
            } catch (e2) {}
        }
        if (msg) showFlashToast(msg);
        deleteCookie('flash_message');
    }
}

function init_htmx_callbacks() {
    $(document).on("click", "button[hx-post], button[hx-get], button[hx-delete], .submit-form-btn", function () {
        if ($(this).attr('_') && $(this).attr('_').includes('htmx:confirm')) {
            return;
        }
        // Directory toggles manage their own expanded/collapsed state. A
        // collapse is a local operation and must never activate the global
        // page-wide waiting cursor. The first expansion is also lightweight
        // enough to use the browser's own HTMX indicator, if configured.
        if ($(this).is('.browser-entry-toggle')) {
            return;
        }
        disable_button($(this));
    });
}

function disable_button(btn) {
    if (btn.prop('disabled')) return;
    btn.data('was-disabled', true);
    btn.prop('disabled', true);
    if (!$(document.body).hasClass("waiting")) {
        document.body.classList.add("waiting");
    };
}

document.addEventListener("htmx:afterRequest", (event) => {
    init_htmx_callbacks();
    $("button[hx-post], button[hx-get], button[hx-delete], .submit-form-btn").each(function () {
        if ($(this).data('was-disabled')) {
            $(this).prop('disabled', false);
            $(this).removeData('was-disabled');
        }
    });
    if ($(document.body).hasClass("waiting")) {
        document.body.classList.remove("waiting");
    };
    var xhr = event.detail.xhr;
    if (xhr && xhr.getResponseHeader("HX-Redirect")) {
        return;
    }
});

document.addEventListener("htmx:responseError", (event) => {
    const xhr = event.detail.xhr;
    const status = xhr ? xhr.status : 0;

    if (status >= 500) {
        showFlashToast({ category: 'error', message: 'Something went wrong. Please try again later.' });
        return;
    }

    const statusLabels = {
        400: 'Bad Request',
        401: 'Unauthorized',
        403: 'Forbidden',
        404: 'Resource Not Found',
        409: 'Conflict',
        422: 'Validation Error',
        429: 'Too Many Requests',
    };

    let detail = '';
    if (xhr && xhr.responseText) {
        try {
            const body = JSON.parse(xhr.responseText);
            if (body.detail) {
                detail = typeof body.detail === 'string' ? body.detail : body.detail.map(e => e.msg || e).join(', ');
            }
        } catch (e) {}
    }

    const label = statusLabels[status] || 'Error';
    const message = detail ? `${label}: ${detail}` : `${label}`;
    showFlashToast({ category: 'error', message });
});

document.addEventListener("flash", (event) => {
    showFlashToast(event.detail);
});

// Pristine modal contents (the loading spinner), captured once per page load so
// modals can be reset after the page is restored from the back/forward cache.
const initialModalContents = new Map();

// A page restored from the back/forward cache comes back exactly as it was left,
// e.g. with a form modal still open after its submit redirected to another page.
// Close and reset any open modal so going back never resurrects a stale form.
window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;

    window.onbeforeunload = null;
    document.body.classList.remove("waiting");
    document.querySelectorAll(".htmx-request").forEach((el) => el.classList.remove("htmx-request"));

    document.querySelectorAll(".modal.show").forEach((modal) => {
        modal.addEventListener("hidden.bs.modal", () => {
            const content = modal.querySelector(".modal-dialog");
            if (content && initialModalContents.has(content.id)) {
                content.innerHTML = initialModalContents.get(content.id);
            }
        }, { once: true });
        bootstrap.Modal.getOrCreateInstance(modal).hide();
    });
});

$(document).ready(function () {
    init_htmx_callbacks();
    checkFlashCookie();
    document.querySelectorAll(".modal > .modal-dialog[id]").forEach((content) => {
        initialModalContents.set(content.id, content.innerHTML);
    });
});