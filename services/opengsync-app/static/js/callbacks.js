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
    render_flash_messages();
});

$(document).ready(function () {
    init_htmx_callbacks();
});