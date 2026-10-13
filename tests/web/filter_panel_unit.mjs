// SPDX-License-Identifier: AGPL-3.0-only
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const helpersPath = path.join(root, "choice/web/filter_panel_helpers.js");
const code = fs.readFileSync(helpersPath, "utf8");

const sandbox = { globalThis: {} };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const H = sandbox.globalThis.ChoiceFilterHelpers;

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

assert(H.isMultiSelect({ multi: true }), "multi true");
assert(H.isMultiSelect({}), "default multi");
assert(!H.isMultiSelect({ multi: false }), "multi false");
assert(!H.isMultiSelect({ mode: "single" }), "mode single");
assert(!H.isMultiSelect({ multi: true, mode: "single" }), "mode single wins");

const opts = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
];
assert(H.filterOptionsByQuery(opts, "alp").length === 1, "filter alpha");
assert(H.filterOptionsByQuery(opts, "").length === 2, "empty query");

console.log("filter_panel_unit ok");
