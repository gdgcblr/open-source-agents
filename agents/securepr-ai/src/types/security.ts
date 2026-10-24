export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export type STRIDECategory =
  | 'Spoofing'
  | 'Tampering'
  | 'Repudiation'
  | 'Information Disclosure'
  | 'Denial of Service'
  | 'Elevation of Privilege';

export type ExposureContext = 'PUBLIC' | 'AUTHENTICATED' | 'INTERNAL' | 'LOCAL_ONLY' | 'UNKNOWN';

export type FindingCategory =
  | 'SECRET'
  | 'JWT_AUTH'
  | 'API_AUTHORIZATION'
  | 'INPUT_VALIDATION'
  | 'DEPENDENCY'
  | 'CONFIG';

export interface Evidence {
  filePath: string;
  startLine: number;
  endLine: number;
  snippet: string;
  sanitized: boolean;
  contextNotes?: string;
}

export interface Finding {
  id: string;
  title: string;
  category: FindingCategory;
  stride: STRIDECategory[];
  description: string;
  scannerName: string;
  rawSeverity: Severity;
  evidence: Evidence[];
  isNewInDiff: boolean;
  cweId?: string;
  owaspApiCategory?: string;
  remediationHint: string;
}

export interface AttackPathStep {
  stepNumber: number;
  filePath: string;
  actionOrState: string;
  associatedFindingId?: string;
}

export interface AttackPathHypothesis {
  id: string;
  title: string;
  summary: string;
  stride: STRIDECategory;
  steps: AttackPathStep[];
  requiresValidation: boolean;
}

export interface RiskScore {
  numericScore: number;
  priorityLevel: Severity;
  likelihood: number;
  impact: number;
  exposureModifier: number;
  confidence: number;
  rationale: string;
}

export interface PrioritizedFinding {
  finding: Finding;
  risk: RiskScore;
  aiExplanation?: string | null;
  aiSuggestedFix?: string | null;
  resolved?: boolean;
}

export interface ScanResult {
  timestamp: string;
  totalFindings: number;
  prioritizedFindings: PrioritizedFinding[];
  attackPathHypotheses: AttackPathHypothesis[];
  redactedItemCount: number;
  passedGate: boolean;
  failOnPolicy: string;
  exposure: ExposureContext;
}

export interface PullRequestPreset {
  id: string;
  prNumber: number;
  title: string;
  author: string;
  branch: string;
  baseBranch: string;
  repo: string;
  exposure: ExposureContext;
  description: string;
  files: Array<{
    path: string;
    status: 'added' | 'modified' | 'deleted';
    diff?: string;
    content: string;
  }>;
}
