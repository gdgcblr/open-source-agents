import type { BrowserContext, Request, Route, WebSocketRoute } from "playwright";
import { sanitizeUrl } from "./sanitization.js";
import type { TargetPolicy } from "./target-policy.js";

export interface BlockedRequest {
  url: string;
  reason: string;
}

// Browser-internal schemes that never touch the network.
const LOCAL_SCHEMES = new Set(["data:", "blob:", "about:"]);

/**
 * Enforces the target policy on every request a browser context makes, not
 * just on the URLs a test plan names: each redirect hop, every subresource
 * (scripts, images, XHR/fetch, iframes) and WebSocket upgrades. Without this,
 * an allowed public page could redirect or fetch into an internal service.
 *
 * Top-level navigations get the full policy (including allowedOrigins);
 * subresources only get the private-network check, so pages can still load
 * assets from public CDNs.
 */
export class NetworkGuard {
  private blockedNavigation: BlockedRequest | undefined;

  constructor(private readonly policy: TargetPolicy) {}

  async install(context: BrowserContext): Promise<void> {
    await context.route("**/*", (route) => this.handleRequest(route));
    await context.routeWebSocket(/.*/, (ws) => this.handleWebSocket(ws));
  }

  /** Returns (and clears) the most recent top-level navigation this guard aborted. */
  takeBlockedNavigation(): BlockedRequest | undefined {
    const blocked = this.blockedNavigation;
    this.blockedNavigation = undefined;
    return blocked;
  }

  private async handleRequest(route: Route): Promise<void> {
    const request = route.request();
    const url = request.url();
    if (LOCAL_SCHEMES.has(new URL(url).protocol)) {
      await route.continue();
      return;
    }

    const isTopLevel = isTopLevelNavigation(request);
    const verdict = await this.policy.evaluateResolved(url, { enforceOrigins: isTopLevel });
    if (!verdict.allowed) {
      await this.block(route, url, verdict.reason, isTopLevel);
      return;
    }

    // Chromium follows redirects without calling route() again, so fetch each
    // hop ourselves and vet the Location before handing the 3xx back to the browser,
    // which then issues the next hop as a fresh (routed) request.
    let response;
    try {
      response = await route.fetch({ maxRedirects: 0 });
    } catch {
      await route.abort("failed").catch(() => {});
      return;
    }
    const location = response.headers()["location"];
    if (response.status() >= 300 && response.status() < 400 && location) {
      const next = new URL(location, url).toString();
      const redirectVerdict = await this.policy.evaluateResolved(next, { enforceOrigins: isTopLevel });
      if (!redirectVerdict.allowed) {
        await this.block(route, next, redirectVerdict.reason, isTopLevel);
        return;
      }
    }
    await route.fulfill({ response });
  }

  private async block(route: Route, url: string, reason: string | undefined, isTopLevel: boolean): Promise<void> {
    if (isTopLevel) {
      this.blockedNavigation = {
        url: sanitizeUrl(url),
        reason: reason ?? `Navigation to "${sanitizeUrl(url)}" is not allowed`,
      };
    }
    await route.abort("blockedbyclient");
  }

  private async handleWebSocket(ws: WebSocketRoute): Promise<void> {
    const httpUrl = ws.url().replace(/^ws/, "http");
    const verdict = await this.policy.evaluateResolved(httpUrl, { enforceOrigins: false });
    if (verdict.allowed) {
      ws.connectToServer();
    } else {
      await ws.close({ code: 1008, reason: "Blocked by target policy" });
    }
  }
}

function isTopLevelNavigation(request: Request): boolean {
  if (!request.isNavigationRequest()) return false;
  try {
    const frame = request.frame();
    return frame.parentFrame() === null;
  } catch {
    // Requests without a frame (e.g. service workers) are never top-level navigations.
    return false;
  }
}
