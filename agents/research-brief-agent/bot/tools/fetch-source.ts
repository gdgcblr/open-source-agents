import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";

const MAX_BYTES = 256_000;
const FETCH_TIMEOUT_MS = 15_000;

function isBlockedHostname(hostname: string): boolean {
  const h = hostname.toLowerCase();
  if (h === "localhost" || h.endsWith(".localhost")) return true;
  if (h === "127.0.0.1" || h === "::1" || h === "0.0.0.0") return true;
  if (h.startsWith("10.")) return true;
  if (h.startsWith("192.168.")) return true;
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(h)) return true;
  return false;
}

function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export default defineTool({
  description:
    "Fetch readable text from a public http(s) URL. Prefer bundled sources when the user wants an offline demo.",
  effect: "read",
  inputSchema: z.object({
    url: z.string().url().describe("Public http or https URL to fetch"),
  }),
  async execute({ url }) {
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      return { ok: false as const, error: "invalid URL" };
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { ok: false as const, error: "only http and https URLs are allowed" };
    }

    if (isBlockedHostname(parsed.hostname)) {
      return {
        ok: false as const,
        error: "local and private network URLs are not allowed",
      };
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    try {
      const res = await fetch(url, {
        signal: controller.signal,
        headers: {
          Accept: "text/html, text/plain, application/json, */*",
          "User-Agent": "research-brief-agent/1.0 (oss demo)",
        },
        redirect: "follow",
      });

      if (!res.ok) {
        return {
          ok: false as const,
          error: `HTTP ${res.status}`,
          finalUrl: res.url,
        };
      }

      const buf = Buffer.from(await res.arrayBuffer());
      const truncated = buf.length > MAX_BYTES;
      const slice = truncated ? buf.subarray(0, MAX_BYTES) : buf;
      let text = slice.toString("utf8");

      const ctype = res.headers.get("content-type") ?? "";
      if (ctype.includes("html")) {
        text = stripHtml(text);
      }

      return {
        ok: true as const,
        finalUrl: res.url,
        contentType: ctype,
        bytes: buf.length,
        truncated,
        text,
      };
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "fetch failed";
      return { ok: false as const, error: message };
    } finally {
      clearTimeout(timer);
    }
  },
});
