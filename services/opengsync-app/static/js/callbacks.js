function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function deleteCookie(name) {
    document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
}

function showFlashToast(msg) {
    Swal.fire({
        position: 'top',
        icon: msg.category || 'success',
        html: `<div style="display: flex; justify-content: center; align-items: center; height: 100%; padding: 0; font-weight: 600;">${msg.message}</div>`,
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
    // render_flash_messages();
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
        404: 'Not Found',
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
    const message = detail ? `${label}: ${detail}` : `${label}. Something went wrong.`;
    showFlashToast({ category: 'error', message });
});

document.addEventListener("flash", (event) => {
    showFlashToast(event.detail);
});

$(document).ready(function () {
    init_htmx_callbacks();
    checkFlashCookie();
});