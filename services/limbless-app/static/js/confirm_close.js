function confirm_close_modal(modal_query){
    return Swal.fire({
        title: "Exit Form?",
        text: "You won't be able to revert this!",
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Yes",
        }).then((result) => {
            if (result.isConfirmed) {
                window.onbeforeunload = null;
                $(modal_query).modal("hide");
                let time_interval;
                Swal.fire({
                    title: "Closed!",
                    icon: "info",
                    timer: 1000,
                    timerProgressBar: true,
                    didOpen: () => {
                        time_interval = setInterval(() => {
                        }, 100);
                    },
                    willClose: () => {
                        clearInterval(time_interval);
                    }
                });
            }
        }
    );
}