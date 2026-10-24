import { describe, expect, it } from "vitest";
import { sanitizeText, sanitizeUrl } from "../../src/security/sanitization.js";

describe("sanitizeText", () => {
  it("redacts a Bearer token", () => {
    const out = sanitizeText('Request failed with header "Authorization: Bearer abc123.def456"');
    expect(out).toContain("Bearer [REDACTED]");
    expect(out).not.toContain("abc123.def456");
  });

  it("redacts a sensitive query param value embedded in text", () => {
    const out = sanitizeText("GET /reset?token=super-secret-value failed");
    expect(out).toContain("token=[REDACTED]");
    expect(out).not.toContain("super-secret-value");
  });

  it("leaves ordinary text untouched", () => {
    const out = sanitizeText("Expected element to be visible but it was not");
    expect(out).toBe("Expected element to be visible but it was not");
  });
});

describe("sanitizeUrl", () => {
  it("redacts a sensitive query parameter in a URL", () => {
    const out = sanitizeUrl("https://example.com/api/login?apikey=sk-live-12345&user=ada");
    expect(out).toContain("apikey=%5BREDACTED%5D");
    expect(out).not.toContain("sk-live-12345");
    expect(out).toContain("user=ada");
  });

  it("passes through a URL with no sensitive parameters", () => {
    const out = sanitizeUrl("https://example.com/signup?step=2");
    expect(out).toBe("https://example.com/signup?step=2");
  });

  it("falls back to text sanitization for a malformed URL", () => {
    const out = sanitizeUrl("not a url with token=abc123");
    expect(out).toContain("token=[REDACTED]");
  });
});
