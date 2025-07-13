const sequence = {
    "A": "T",
    "T": "A",
    "G": "C",
    "C": "G"
}

function reverse_complement(str) {
    var rev = str.split("").reverse().join("");

    return rev.replace(/A|T|G|C/g, function(matched) {
        return sequence[matched];
    });
}