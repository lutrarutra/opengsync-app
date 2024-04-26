function confirm_close_modal(modal_query){
    return Swal.fire({
        title: "Cancel Form?",
        text: "You won't be able to revert this!",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#3085d6",
        cancelButtonColor: "#d33",
        confirmButtonText: "Yes",
        }).then((result) => {
            if (result.isConfirmed) {
                window.onbeforeunload = null;
                $(modal_query).modal("hide");
                let time_interval;
                Swal.fire({
                    title: "Deleted!",
                    text: "Your file has been deleted.",
                    icon: "success",
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