// Assert-based checks for chat's markdown repair, its sources and the settings form. Run: npm test (in frontend/).
import assert from "node:assert/strict";
import { normaliseMarkdown as fix } from "../src/features/chat/markdown.ts";
import { sourcesFromResponse } from "../src/features/chat/sources.ts";
import { withEdits } from "../src/contexts/settingsEdits.ts";

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

// A source keeps the backend's number, which is the [N] in the answer, even when a turn's run 2, 5.
const sources = sourcesFromResponse({
  citations: [{ id: 2, title: "A" }, { id: 5, title: "B", authors: "Li", year: 2020 }],
  snippets: [{ citation_id: 5, snippet: "text", title: "B", page: 3 }, { citation_id: 2, snippet: "other", title: "A", page: null }],
});
assert.deepEqual(sources.map((s) => s.documentId), ["2", "5"]);
assert.equal(sources[1].snippets[0].text, "text");
assert.equal(sources[1].snippets[0].pageNumber, 3);
assert.equal(sources[0].snippets[0].pageNumber, undefined);
assert.equal(sources[0].author, "Unknown");

// Unsaved edits sit over the saved settings, whatever those become.
const saved = {
  theme: "light", zoteroPath: "/z", activeProviderId: "ollama",
  providers: { openai: { enabled: true, credentials: { api_key: "•••abc", base_url: "u" } } },
};
const edits = { zoteroPath: "/typed", providers: { openai: { credentials: { base_url: "v" } }, groq: { enabled: true } } };
const form = withEdits({ ...saved, theme: "dark" }, edits);
assert.equal(form.theme, "dark");
assert.equal(form.zoteroPath, "/typed");
assert.deepEqual(form.providers.openai, { enabled: true, credentials: { api_key: "•••abc", base_url: "v" } });
assert.deepEqual(form.providers.groq, { enabled: true, credentials: {} });
assert.equal(JSON.stringify(withEdits(saved, {})), JSON.stringify(saved)); // clean form, Save stays off
assert.equal(JSON.stringify(withEdits(saved, { zoteroPath: "/z" })), JSON.stringify(saved)); // typed back to the saved value

// Credentials need the active provider in the POST for the backend to reload them; nothing else does.

console.log("chat checks passed");
