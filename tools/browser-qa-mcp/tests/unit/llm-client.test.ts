import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AnthropicProvider, GeminiProvider, getDefaultProvider, isPlannerConfigured } from "../../src/llm/client.js";

const ENV_KEYS = ["LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL"] as const;
let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = {};
  for (const key of ENV_KEYS) {
    saved[key] = process.env[key];
    delete process.env[key];
  }
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
});

describe("isPlannerConfigured", () => {
  it("is false when neither key is set", () => {
    expect(isPlannerConfigured()).toBe(false);
  });

  it("is true when only ANTHROPIC_API_KEY is set", () => {
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    expect(isPlannerConfigured()).toBe(true);
  });

  it("is true when only GEMINI_API_KEY is set", () => {
    process.env.GEMINI_API_KEY = "gm-test";
    expect(isPlannerConfigured()).toBe(true);
  });
});

describe("getDefaultProvider", () => {
  it("throws a clear error when neither key is set", () => {
    expect(() => getDefaultProvider()).toThrow(/requires either ANTHROPIC_API_KEY or GEMINI_API_KEY/);
  });

  it("returns an AnthropicProvider when only ANTHROPIC_API_KEY is set", () => {
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    expect(getDefaultProvider()).toBeInstanceOf(AnthropicProvider);
  });

  it("returns a GeminiProvider when only GEMINI_API_KEY is set", () => {
    process.env.GEMINI_API_KEY = "gm-test";
    expect(getDefaultProvider()).toBeInstanceOf(GeminiProvider);
  });

  it("throws an ambiguity error when both keys are set and LLM_PROVIDER is unset", () => {
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    process.env.GEMINI_API_KEY = "gm-test";
    expect(() => getDefaultProvider()).toThrow(/Set LLM_PROVIDER=anthropic or LLM_PROVIDER=gemini/);
  });

  it("respects LLM_PROVIDER=gemini when both keys are set", () => {
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    process.env.GEMINI_API_KEY = "gm-test";
    process.env.LLM_PROVIDER = "gemini";
    expect(getDefaultProvider()).toBeInstanceOf(GeminiProvider);
  });

  it("respects LLM_PROVIDER=anthropic when both keys are set", () => {
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    process.env.GEMINI_API_KEY = "gm-test";
    process.env.LLM_PROVIDER = "anthropic";
    expect(getDefaultProvider()).toBeInstanceOf(AnthropicProvider);
  });

  it("throws when LLM_PROVIDER names a provider whose key is missing", () => {
    process.env.LLM_PROVIDER = "anthropic";
    process.env.GEMINI_API_KEY = "gm-test";
    expect(() => getDefaultProvider()).toThrow(/ANTHROPIC_API_KEY is not set/);
  });

  it("throws on an unrecognized LLM_PROVIDER value", () => {
    process.env.LLM_PROVIDER = "openai";
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
    expect(() => getDefaultProvider()).toThrow(/Unknown LLM_PROVIDER "openai"/);
  });

  it("is case-insensitive for LLM_PROVIDER", () => {
    process.env.LLM_PROVIDER = "GEMINI";
    process.env.GEMINI_API_KEY = "gm-test";
    expect(getDefaultProvider()).toBeInstanceOf(GeminiProvider);
  });
});
