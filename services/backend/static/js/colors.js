function update_pipet_clr(element, amount_ul) {
    if (amount_ul > 2.0) {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-green");
    } else if (amount_ul > 1.0) {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-yellow");
    } else {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-red");
    }
}

function update_molarity_clr(element, molarity) {
    if (1.0 < molarity && molarity < 5.0) {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-green");
    } else if (molarity < 0.5 || 10.0 < molarity) {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-red");
    } else if (molarity < 1.0 || 5.0 < molarity) {
        element.removeClass("cemm-red cemm-yellow cemm-green").addClass("cemm-yellow");
    }
}