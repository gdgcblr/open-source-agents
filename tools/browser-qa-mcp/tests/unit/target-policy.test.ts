import { describe, expect, it } from "vitest";
import { TargetPolicy } from "../../src/security/target-policy.js";

describe("TargetPolicy", () => {
  it("blocks loopback targets by default", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://127.0.0.1:4000/signup").allowed).toBe(false);
  });

  it("allows loopback targets when allowLocalDev is explicitly set", () => {
    const policy = new TargetPolicy({ allowLocalDev: true });
    expect(policy.evaluate("http://127.0.0.1:4000/signup").allowed).toBe(true);
  });

  it("blocks a link-local/cloud-metadata address without allowLocalDev", () => {
    const policy = new TargetPolicy({ allowLocalDev: false });
    expect(policy.evaluate("http://169.254.169.254/latest/meta-data").allowed).toBe(false);
  });

  it("rejects unsupported protocols", () => {
    const policy = new TargetPolicy({ allowLocalDev: true });
    expect(policy.evaluate("file:///etc/passwd").allowed).toBe(false);
  });

  it("enforces an explicit allowed-origin list when provided", () => {
    const policy = new TargetPolicy({ allowLocalDev: true, allowedOrigins: ["http://127.0.0.1:4000"] });
    expect(policy.evaluate("http://127.0.0.1:4000/signup").allowed).toBe(true);
    expect(policy.evaluate("http://127.0.0.1:5000/signup").allowed).toBe(false);
  });

  it("rejects malformed URLs", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("not a url").allowed).toBe(false);
  });

  it("allows a public origin with no local-dev opt-in needed", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("https://example.com/signup").allowed).toBe(true);
  });

  it("blocks the bracketed IPv6 loopback address by default", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://[::1]:4000/signup").allowed).toBe(false);
  });

  it("allows the bracketed IPv6 loopback address with allowLocalDev", () => {
    const policy = new TargetPolicy({ allowLocalDev: true });
    expect(policy.evaluate("http://[::1]:4000/signup").allowed).toBe(true);
  });

  it("blocks an IPv6 link-local address by default", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://[fe80::1]/").allowed).toBe(false);
  });

  it("blocks an IPv6 unique-local address by default", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://[fd12:3456:789a::1]/").allowed).toBe(false);
  });

  it("blocks an IPv4-mapped IPv6 loopback address by default", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://[::ffff:127.0.0.1]/").allowed).toBe(false);
  });

  it("allows a public IPv6 address with no local-dev opt-in needed", () => {
    const policy = new TargetPolicy({});
    expect(policy.evaluate("http://[2001:4860:4860::8888]/").allowed).toBe(true);
  });

  it("blocks a public-looking hostname that resolves to a private address", async () => {
    const policy = new TargetPolicy({ resolveHost: async () => ["93.184.216.34", "10.0.0.5"] });
    const verdict = await policy.evaluateResolved("https://internal.example.com/");
    expect(verdict.allowed).toBe(false);
    expect(verdict.reason).toMatch(/10\.0\.0\.5/);
  });

  it("allows a hostname whose every address is public", async () => {
    const policy = new TargetPolicy({ resolveHost: async () => ["93.184.216.34"] });
    expect((await policy.evaluateResolved("https://example.com/")).allowed).toBe(true);
  });

  it("fails closed when DNS resolution fails", async () => {
    const policy = new TargetPolicy({
      resolveHost: async () => {
        throw new Error("ENOTFOUND");
      },
    });
    expect((await policy.evaluateResolved("https://nope.invalid/")).allowed).toBe(false);
  });

  it("skips DNS entirely with allowLocalDev", async () => {
    const policy = new TargetPolicy({
      allowLocalDev: true,
      resolveHost: async () => {
        throw new Error("should not be called");
      },
    });
    expect((await policy.evaluateResolved("http://localhost:4000/")).allowed).toBe(true);
  });

  it("applies allowedOrigins only when enforceOrigins is set", () => {
    const policy = new TargetPolicy({ allowedOrigins: ["https://app.example.com"] });
    expect(policy.evaluate("https://cdn.example.net/a.js", { enforceOrigins: false }).allowed).toBe(true);
    expect(policy.evaluate("https://cdn.example.net/a.js").allowed).toBe(false);
  });

  it("blocks 0.0.0.0, CGNAT and multicast ranges", () => {
    const policy = new TargetPolicy({});
    for (const url of ["http://0.0.0.0/", "http://100.64.0.1/", "http://224.0.0.1/", "http://app.localhost/"]) {
      expect(policy.evaluate(url).allowed).toBe(false);
    }
  });
});
