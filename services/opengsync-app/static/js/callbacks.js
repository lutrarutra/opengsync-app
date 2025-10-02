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

document.addEventListener("htmx:afterRequest", () => {
    init_htmx_callbacks();
});

document.body.addEventListener('htmx:afterRequest', function () {
    document.body.classList.remove("waiting");
    $("button[hx-post], button[hx-get], button[hx-delete], .submit-form-btn").each(function () {
        if ($(this).data('was-disabled')) {
            $(this).prop('disabled', false);
            $(this).removeData('was-disabled');
        }
    });
});