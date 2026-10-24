import assert from "node:assert/strict";
import { test, before, after } from "node:test";
import { readFile, access } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
let server, ui;
before(async () => {
  server = await createServer({
    root,
    server: { middlewareMode: true },
    appType: "custom",
  });
  ui = await server.ssrLoadModule("/src/App.jsx");
});
after(async () => {
  await server?.close();
});
const photo = {
  id: "abc",
  filename: "<unsafe>.jpg",
  photographer: "A & B",
  role: "organizer",
  width: 100,
  height: 80,
  picked: 0,
  flags: ["Soft image"],
  assessment: {
    score: 5,
    moment: 7,
    composition: 5,
    expressions: 3,
    reason: "A <good> moment",
    caption: "A quiet frame.",
  },
};
test("photo cards escape untrusted metadata and do not render numeric false as zero", () => {
  const html = renderToStaticMarkup(
    createElement(ui.PhotoCard, { photo, onSelect: () => {} }),
  );
  assert.match(html, /&lt;unsafe&gt;/);
  assert.match(html, /A &amp; B/);
  assert.doesNotMatch(html, />0</);
  assert.doesNotMatch(html, /AI pick/);
  assert.match(html, /loading="lazy"/);
  assert.match(html, /\/api\/photos\/abc\/thumb/);
  assert.doesNotMatch(html, /\/original/);
  assert.match(
    renderToStaticMarkup(
      createElement(ui.PhotoCard, {
        photo: { ...photo, picked: 1 },
        onSelect: () => {},
      }),
    ),
    /AI pick/,
  );
});
test("details retain scores, hints, captions and separate original and credited exports", () => {
  const html = renderToStaticMarkup(
    createElement(ui.PhotoDetails, {
      photo,
      close: () => {},
      notify: () => {},
    }),
  );
  for (const text of [
    "AI score 5/10",
    "Soft image",
    "A quiet frame.",
    "moment",
    "composition",
    "expressions",
    "/original",
    "/export?watermark=",
  ])
    assert.ok(html.includes(text), text);
  assert.match(html, /A &lt;good&gt; moment/);
  assert.match(html, /aria-labelledby="photo-title"/);
});
test("production entry uses bundled local assets and ships dark mode", async () => {
  const html = await readFile(
    resolve(root, "../curator/static/index.html"),
    "utf8",
  );
  assert.match(html, /class="dark"/);
  assert.match(html, /<title>AfterClick<\/title>/);
  assert.match(html, /name="color-scheme" content="dark"/);
  const assets = [...html.matchAll(/(?:src|href)="(\/static\/[^\"]+)"/g)].map(
    (m) => m[1],
  );
  assert.ok(assets.length >= 2);
  for (const asset of assets)
    await access(resolve(root, "../curator", asset.slice(1)));
  assert.doesNotMatch(html, /https?:\/\//);
});

test("attendee screen has only gallery and face search; organizer has import and agent composer", () => {
  const attendee = renderToStaticMarkup(
    createElement(ui.default, { initialRole: "/attendee" }),
  );
  assert.match(attendee, /Find my photos/);
  assert.doesNotMatch(
    attendee,
    /Import folder|Ask the event agent|Event agent/,
  );
  const organizer = renderToStaticMarkup(
    createElement(ui.default, { initialRole: "/organizer" }),
  );
  assert.match(organizer, /AfterClick/);
  assert.doesNotMatch(organizer, /Event Photo Curator/);
  assert.match(organizer, /Import folder/);
  assert.match(organizer, /Ask the event agent/);
  assert.match(organizer, /Photo directory on this laptop/);
});
test("matching faces render normalized dotted box positions without changing the image", () => {
  const html = renderToStaticMarkup(
    createElement(ui.PhotoCard, {
      photo: {
        ...photo,
        matched_faces: [{ box: [0.1, 0.2, 0.3, 0.4], ambiguous: true }],
      },
      onSelect: () => {},
    }),
  );
  assert.match(html, /face-box ambiguous/);
  assert.match(html, /left:10%/);
  assert.match(html, /top:20%/);
  assert.match(html, /width:30%/);
  const invalid = renderToStaticMarkup(
    createElement(ui.FaceBoxes, { faces: [{ box: [-1, 0, 0.5, 0.5] }] }),
  );
  assert.doesNotMatch(invalid, /class="face-box"/);
});
