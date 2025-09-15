document.addEventListener("DOMContentLoaded", function () {
    var hash = window.location.hash;
    if (!hash) {
        const params = new URLSearchParams(window.location.search);
        hash = "#" + params.get("tab");
    }
    if (hash) {
        const trigger = document.querySelector(`button[data-bs-target="${hash}"]`);
        if (trigger) {
            const tab = new bootstrap.Tab(trigger);
            tab.show();
        }
    }
});

document.querySelectorAll('.page-tabs button[data-bs-toggle="tab"]').forEach(button => {
    button.addEventListener('shown.bs.tab', function (event) {
        const hash = event.target.getAttribute('data-bs-target');
        if (hash) {
            history.replaceState(null, null, hash);
        }
    });
});
