// Address bar state of the htmx tables (static/js/table.js): each table keeps its state under its own prefix
// (`lib.q=…&lib.page=2`), next to other tables' and the page's own parameters. Run with `node --test`.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

// table.js registers listeners on load; stubs are enough for the pure helpers tested here
const noop = () => {};
const sandbox = {
    module: { exports: {} },
    URLSearchParams,
    WeakMap,
    document: { body: { addEventListener: noop }, addEventListener: noop, querySelectorAll: () => [] },
    window: { location: { search: "", pathname: "/", hash: "" }, addEventListener: noop },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/js/table.js"), "utf8"), sandbox);
const { tableStateFromSearch, tableSearchWithState } = sandbox.module.exports;

test("reads only the parameters of its own table, without the prefix", () => {
    const search = "?tab=x&lib.q=pbmc&lib.status_in=5,6&smp.page=3&lib.=empty&library.q=other";
    assert.deepEqual({ ...tableStateFromSearch(search, "lib") }, { q: "pbmc", status_in: "5,6" });
    assert.deepEqual({ ...tableStateFromSearch(search, "smp") }, { page: "3" });
    assert.deepEqual({ ...tableStateFromSearch("", "lib") }, {});
});

test("replaces its own parameters and keeps everything else", () => {
    const search = "?tab=libraries&lib.q=old&lib.page=4&smp.q=keep";
    assert.equal(
        tableSearchWithState(search, "lib", { q: "new value", order_by: "name:asc" }),
        "?tab=libraries&smp.q=keep&lib.q=new+value&lib.order_by=name%3Aasc",
    );
});

test("an empty state removes the table's parameters, and empty values are not written", () => {
    assert.equal(tableSearchWithState("?lib.q=a&lib.page=2", "lib", {}), "");
    assert.equal(tableSearchWithState("?x=1&lib.q=a", "lib", { q: "", page: null }), "?x=1");
});

test("round trip: what is written is read back", () => {
    const state = { q: 'owner:chen "liver organoid"', status_in: "5,6", page: "2" };
    const search = tableSearchWithState("?tab=t", "lib", state);
    assert.deepEqual({ ...tableStateFromSearch(search, "lib") }, state);
});

test("search terms for highlighting: field prefixes, quotes and # are dropped, 1-letter words ignored", () => {
    const { searchTerms } = sandbox.module.exports;
    assert.deepEqual([...searchTerms('owner:chen "liver org" #12 a 7 pbmc')], ["chen", "liver org", "12", "7", "pbmc"]);
    assert.deepEqual([...searchTerms("")], []);
    assert.deepEqual([...searchTerms(undefined)], []);
});
