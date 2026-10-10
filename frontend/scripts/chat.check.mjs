// Assert-based checks for legacy chat's markdown repair. Run: npm test (in frontend/).
import assert from "node:assert/strict";
import { normaliseMarkdown as fix } from "../src/features/chat/markdown.ts";

// Ordinary inline bold is left alone.
const typical = "**Adversarial examples** are small changes [1].\n\n**Why it works**\n\n- Transfer [3].";
assert.equal(fix(typical), typical);
assert.equal(fix("A **key** point, and **another**."), "A **key** point, and **another**.");

// The broken shapes the repair exists for.
assert.equal(fix("**Title\n\n**\n\nBody"), "**Title**\n\nBody");
assert.equal(fix("Intro\n**\n\nTitle\n\n**"), "Intro\n\n**Title**");
assert.equal(fix("Intro text\n**Heading**\nBody"), "Intro text\n\n**Heading**\n\nBody");
assert.equal(fix("**Heading**Body runs on"), "**Heading**\n\nBody runs on");

// A bold label followed by a space stays on its line.
assert.equal(fix("**Note:** keep inline"), "**Note:** keep inline");

console.log("chat checks passed");
