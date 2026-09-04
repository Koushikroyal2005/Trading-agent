import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("dashboard contains product-specific accessible surfaces", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.match(page, /VECTOR/);
  assert.match(page, /AGENT NETWORK/);
  assert.match(page, /aria-label="Symbol"/);
  assert.match(page, /\/ws\/market/);
  assert.match(page, /\/api\/v1\/market\/history/);
  assert.match(page, /\/api\/v1\/market\/quotes/);
  assert.match(page, /setTimeout\(connect, 2_000\)/);
  assert.match(page, /verified quote polling active/);
  assert.match(page, /\/api\/v1\/market\/history/);
  assert.match(page, /\/api\/v1\/market\/quotes/);
  assert.match(page, /setTimeout\(connect, 2_000\)/);
  assert.match(page, /verified quote polling active/);
  assert.match(page, /analysis-only/);
  assert.match(page, /confirm\("Enable automated Alpaca PAPER orders/);
  assert.doesNotMatch(page, /104,284|842\.16|checkpoint 42|4 positions/);
  assert.match(layout, /Agentic Trading Desk/);
  assert.doesNotMatch(page + layout, /SkeletonPreview|codex-preview/);
});
