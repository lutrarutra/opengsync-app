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