function render_flash_messages() {
    $.ajax({
        url: "/retrieve_flash_messages",
        type: "GET"
    }).done(function(data) {
        let messages = Array.isArray(data) ? data : (data && data.messages ? data.messages : []);
        if (!messages.length) {
            return;
        }
        showOneFlashFromList(messages, 0);
    });
}

function showOneFlashFromList(messages, index) {
    if (index >= messages.length) {
        return;  // No more messages
    }
    const msg = messages[index];
    Swal.fire({
        position: 'top',
        icon: msg.category || 'success',
        html: `<div style="display: flex; justify-content: center; align-items: center; height: 100%; padding: 0; font-weight: 600;">${msg.message}</div>`,
        showConfirmButton: false,
        timer: msg.category === 'error' ? null : 1000,
        toast: true,
        showCloseButton: true,
        willClose: function() {
            showOneFlashFromList(messages, index + 1);
        }
    });
}