const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const window = {};
vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "../static/js/jss-object-column.js"), "utf8"),
    { window },
);

function sorted(sortings, title, direction, values) {
    const comparator = sortings.find((sorting) => sorting.title === title).sorting(direction);
    return [...values].sort(comparator).map((value) => value[2]);
}

test("DBObject IDs use stored values, including hidden and duplicate-name IDs", () => {
    const values = [
        [0, "alpha", "Alpha [10]"],
        [1, "twin [8]", "Twin [8]"],
        [2, "beta", "Beta [2]"],
        [3, "twin [7]", "Twin [7]"],
        [4, "", ""],
        [5, "", "Unknown [4]"],
    ];
    assert.deepEqual(sorted(window.jssObjectSortings, "ID", 0, values), [
        "Beta [2]", "Unknown [4]", "Twin [7]", "Twin [8]", "Alpha [10]", "",
    ]);
    assert.deepEqual(sorted(window.jssObjectSortings, "ID", 1, values), [
        "Alpha [10]", "Twin [8]", "Twin [7]", "Unknown [4]", "Beta [2]", "",
    ]);
});

test("Query IDs sort numerically and do not interpret new text as an ID", () => {
    const values = [
        [0, "alpha", 10],
        [1, "twin [2]", 2],
        [2, "twin [3]", 3],
        [3, "new [1]", "new [1]"],
        [4, "", ""],
    ];
    assert.deepEqual(sorted(window.jssQuerySortings, "ID", 0, values), [2, 3, 10, "new [1]", ""]);
    assert.deepEqual(sorted(window.jssQuerySortings, "ID", 1, values), ["new [1]", 10, 3, 2, ""]);
});

test("Name sorting preserves each column type's existing behavior", () => {
    const objects = [
        [0, "sample 10", "Sample 10 [1]"],
        [1, "sample 2", "Sample 2 [2]"],
        [2, "", ""],
    ];
    assert.deepEqual(sorted(window.jssObjectSortings, "name", 0, objects), ["Sample 2 [2]", "Sample 10 [1]", ""]);
    const queries = [[0, "sample 2", 2], [1, "sample 10", 10], [2, "", ""]];
    assert.deepEqual(sorted(window.jssQuerySortings, "name", 0, queries), [10, 2, ""]);
    assert.deepEqual(sorted(window.jssQuerySortings, "name", 1, queries), [2, 10, ""]);
});
