import { existsSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { BrowserManager } from "../../src/runner/browser-manager.js";
import { TargetPolicy } from "../../src/security/target-policy.js";

// Sandboxed CI images ship Chromium here; elsewhere fall back to the one `playwright install` downloaded.
if (!process.env.PLAYWRIGHT_CHROMIUM_PATH && existsSync("/opt/pw-browsers/chromium")) {
  process.env.PLAYWRIGHT_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
}

// Stands in for an internal service: anything that reaches it is an SSRF.
let internal: Server;
let internalHits: string[] = [];
let app: Server;
let appOrigin: string;
let internalOrigin: string;

function listen(server: Server): Promise<string> {
  return new Promise((resolve) =>
    server.listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`)),
  );
}

beforeAll(async () => {
  internal = createServer((req, res) => {
    internalHits.push(req.url ?? "");
    res.end("secret");
  });
  internalOrigin = await listen(internal);

  app = createServer((req, res) => {
    if (req.url === "/redirect") {
      res.writeHead(302, { location: `${internalOrigin}/admin` });
      res.end();
    } else {
      res.setHeader("content-type", "text/html");
      res.end(`<title>ok</title><img src="${internalOrigin}/pixel">`);
    }
  });
  appOrigin = await listen(app);
});

afterAll(async () => {
  await new Promise((r) => internal.close(r));
  await new Promise((r) => app.close(r));
});

// Both servers are on loopback, so allowLocalDev is required; allowedOrigins stands in for "the public app".
describe("NetworkGuard (real Chromium)", () => {
  it("blocks a redirect from an allowed origin to a disallowed one", async () => {
    internalHits = [];
    const policy = new TargetPolicy({ allowLocalDev: true, allowedOrigins: [appOrigin] });
    const browser = new BrowserManager();
    await browser.launch();
    try {
      const session = await browser.openTestSession(policy);
      await expect(session.page.goto(`${appOrigin}/redirect`)).rejects.toThrow();
      expect(session.networkGuard.takeBlockedNavigation()?.reason).toMatch(/not in the allowed origin list/);
      expect(internalHits).toEqual([]);
    } finally {
      await browser.close();
    }
  }, 20_000);

  it("blocks subresource requests to a private address", async () => {
    internalHits = [];
    const policy = new TargetPolicy({ allowLocalDev: false, resolveHost: async () => ["93.184.216.34"] });
    // Treat the app as public by checking subresources only: the page itself is loaded via setContent.
    const browser = new BrowserManager();
    await browser.launch();
    try {
      const session = await browser.openTestSession(policy);
      await session.page.setContent(`<img src="${internalOrigin}/pixel"><script src="${internalOrigin}/x.js"></script>`);
      await session.page.waitForTimeout(300);
      expect(internalHits).toEqual([]);
    } finally {
      await browser.close();
    }
  }, 20_000);
});
