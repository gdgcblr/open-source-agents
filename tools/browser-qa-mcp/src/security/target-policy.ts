import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export type HostResolver = (hostname: string) => Promise<string[]>;

export interface TargetPolicyOptions {
  /** Exact origins (scheme + host + port) permitted, e.g. "http://127.0.0.1:4000". */
  allowedOrigins?: string[];
  /** Explicit opt-in required to test loopback/private-network destinations. */
  allowLocalDev?: boolean;
  /** Overridable for tests. Defaults to the OS resolver (all A/AAAA records). */
  resolveHost?: HostResolver;
}

export interface TargetPolicyResult {
  allowed: boolean;
  reason?: string;
}

export interface EvaluateOptions {
  /**
   * Whether the allowedOrigins list applies. True for top-level navigations;
   * false for subresources (scripts, fonts, XHR, iframes), which may come from
   * any public origin but must still never reach a private network.
   */
  enforceOrigins?: boolean;
}

const defaultResolver: HostResolver = async (hostname) =>
  (await lookup(hostname, { all: true, verbatim: true })).map((entry) => entry.address);

/**
 * Navigation/target gate: deny by default, and require an explicit opt-in
 * before any loopback or private-network address can be reached.
 *
 * `evaluate()` checks the URL literal. `evaluateResolved()` additionally
 * resolves the hostname and rejects it if any returned address is private, so
 * a public-looking name that points at an internal IP is caught. The runner
 * applies `evaluateResolved()` to every browser request, including each
 * redirect hop and subresource (see network-guard.ts).
 *
 * Residual risk: Chromium does its own DNS resolution after this check, so a
 * rebinding attacker with a very short TTL can still race it. Only
 * network-level egress filtering closes that gap (see README).
 */
export class TargetPolicy {
  private readonly resolveHost: HostResolver;
  private readonly resolvedVerdicts = new Map<string, Promise<TargetPolicyResult>>();

  constructor(private readonly options: TargetPolicyOptions) {
    this.resolveHost = options.resolveHost ?? defaultResolver;
  }

  evaluate(rawUrl: string, { enforceOrigins = true }: EvaluateOptions = {}): TargetPolicyResult {
    let parsed: URL;
    try {
      parsed = new URL(rawUrl);
    } catch {
      return { allowed: false, reason: `Invalid URL: "${rawUrl}"` };
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { allowed: false, reason: `Unsupported protocol "${parsed.protocol}"; only http/https are permitted` };
    }

    if (isLoopbackOrPrivateHost(parsed.hostname) && !this.options.allowLocalDev) {
      return {
        allowed: false,
        reason: `Target host "${parsed.hostname}" is a loopback/private-network address; set allowLocalDev to permit local testing`,
      };
    }

    if (enforceOrigins && this.options.allowedOrigins && this.options.allowedOrigins.length > 0) {
      if (!this.options.allowedOrigins.includes(parsed.origin)) {
        return { allowed: false, reason: `Origin "${parsed.origin}" is not in the allowed origin list` };
      }
    }

    return { allowed: true };
  }

  async evaluateResolved(rawUrl: string, options: EvaluateOptions = {}): Promise<TargetPolicyResult> {
    const literal = this.evaluate(rawUrl, options);
    if (!literal.allowed || this.options.allowLocalDev) return literal;

    const hostname = stripBrackets(new URL(rawUrl).hostname.toLowerCase());
    if (isIP(hostname)) return literal;

    let verdict = this.resolvedVerdicts.get(hostname);
    if (!verdict) {
      verdict = this.checkResolvedAddresses(hostname);
      this.resolvedVerdicts.set(hostname, verdict);
    }
    return verdict;
  }

  private async checkResolvedAddresses(hostname: string): Promise<TargetPolicyResult> {
    let addresses: string[];
    try {
      addresses = await this.resolveHost(hostname);
    } catch (err) {
      return { allowed: false, reason: `Could not resolve "${hostname}": ${(err as Error).message}` };
    }
    if (addresses.length === 0) {
      return { allowed: false, reason: `"${hostname}" did not resolve to any address` };
    }

    const privateAddress = addresses.find((address) => isLoopbackOrPrivateHost(address));
    if (privateAddress) {
      return {
        allowed: false,
        reason: `Target host "${hostname}" resolves to loopback/private-network address ${privateAddress}; set allowLocalDev to permit local testing`,
      };
    }
    return { allowed: true };
  }
}

function isLoopbackOrPrivateHost(hostname: string): boolean {
  // Node's URL parser returns IPv6 hostnames bracketed, e.g. "[::1]".
  const host = stripBrackets(hostname.toLowerCase());
  if (host === "localhost" || host.endsWith(".localhost")) return true;

  if (isIPv4(host)) return isPrivateIPv4(host.split(".").map(Number));

  if (host === "::1" || host === "::") return true; // IPv6 loopback / unspecified
  if (host.startsWith("fe80:")) return true; // IPv6 link-local (fe80::/10)
  if (host.startsWith("fc") || host.startsWith("fd")) return true; // IPv6 unique-local (fc00::/7)

  const ipv4MappedDotted = host.match(/^::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/);
  if (ipv4MappedDotted) return isPrivateIPv4(ipv4MappedDotted[1].split(".").map(Number));

  // Node normalizes an IPv4-mapped IPv6 address to compressed hex groups
  // (e.g. "::ffff:127.0.0.1" becomes "::ffff:7f00:1"), not the dotted form above.
  const ipv4MappedHex = host.match(/^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/);
  if (ipv4MappedHex) {
    const high = parseInt(ipv4MappedHex[1], 16);
    const low = parseInt(ipv4MappedHex[2], 16);
    return isPrivateIPv4([high >> 8, high & 0xff, low >> 8, low & 0xff]);
  }

  return false;
}

function isPrivateIPv4([a, b]: number[]): boolean {
  if (a === 0) return true; // "this network"; 0.0.0.0 reaches the local host on most systems
  if (a === 127) return true; // loopback
  if (a === 10) return true; // private
  if (a === 172 && b >= 16 && b <= 31) return true; // private
  if (a === 192 && b === 168) return true; // private
  if (a === 169 && b === 254) return true; // link-local, includes cloud metadata (169.254.169.254)
  if (a === 100 && b >= 64 && b <= 127) return true; // carrier-grade NAT, often internal in cloud VPCs
  if (a >= 224) return true; // multicast and reserved
  return false;
}

function isIPv4(host: string): boolean {
  return /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host);
}

function stripBrackets(host: string): string {
  return host.startsWith("[") && host.endsWith("]") ? host.slice(1, -1) : host;
}
