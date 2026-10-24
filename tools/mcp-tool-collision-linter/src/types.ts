/** A tool as exposed by one MCP server. */
export interface ToolDef {
  /** Server the tool came from (key in the MCP config). */
  server: string;
  /** Tool name as the server reports it. */
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

/** A tool once loaded into the shared tool list the model sees. */
export interface LoadedTool extends ToolDef {
  /** Unique, provider-safe id, e.g. `notes__search`. This is what the model calls. */
  id: string;
}

/** A pair of tools flagged by static analysis as likely to be confused. */
export interface CandidatePair {
  a: LoadedTool;
  b: LoadedTool;
  /** Combined static similarity, 0..1. */
  score: number;
  signals: {
    descriptionSimilarity: number;
    nameOverlap: number;
    paramOverlap: number;
    sameName: boolean;
    sharedTerms: string[];
  };
}

/** A user request written to test whether the model picks the intended tool. */
export interface Probe {
  prompt: string;
  /** Id of the tool that should handle this prompt. */
  intended: string;
}

export interface ProbeResult extends Probe {
  /** Id of the tool the model chose, or null if it chose none. */
  chosen: string | null;
}

export interface PairEvaluation {
  pair: CandidatePair;
  probes: ProbeResult[];
  /** Fraction of probes routed to the *other* tool in the pair. */
  confusionRate: number;
  /** Fraction routed to the intended tool. */
  accuracy: number;
  aToB: number;
  bToA: number;
  /** Probes routed to a third tool or to no tool. */
  elsewhere: number;
  severity: "high" | "medium" | "low" | "none";
  rewrite?: RewriteSuggestion;
}

export interface RewriteSuggestion {
  descriptions: Record<string, string>;
  rationale: string;
  /** Present when rewrites were re-tested with --verify-rewrites. */
  after?: {
    confusionRate: number;
    accuracy: number;
  };
}

export interface ToolChoiceRequest {
  prompt: string;
  tools: LoadedTool[];
}

/** Anything that can (a) pick a tool for a prompt and (b) generate text. */
export interface Provider {
  readonly name: string;
  /** Returns the id of the tool the model chose, or null. */
  chooseTool(req: ToolChoiceRequest): Promise<string | null>;
  /** Free-text completion, used for probe generation and rewrites. Absent for offline mode. */
  complete?(system: string, user: string): Promise<string>;
}

export interface LintReport {
  generatedAt: string;
  provider: string;
  toolCount: number;
  servers: string[];
  candidates: CandidatePair[];
  evaluations: PairEvaluation[];
}
