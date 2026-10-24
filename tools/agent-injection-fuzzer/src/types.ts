export type Outcome =
  | 'PASS'
  | 'BLOCKED'
  | 'LEAK'
  | 'UNAUTHORIZED_CALL'
  | 'NO_DELIVERY'
  | 'ERROR';

export interface Payload {
  id: string;
  family: string;
  text: string;
}

export interface Trace {
  delivered: boolean;
  executedTools: string[];
  blockedTools: string[];
  agentText: string;
}

export interface CaseConfig {
  task: string;
  deliveryTool: string;
  sensitiveTool: string;
  canary: string;
}

export interface SentEmail {
  to: string;
  body: string;
}

export interface CaseResult {
  payload: Payload;
  locked: boolean;
  outcome: Outcome;
  trace: Trace;
  // Ground truth: emails the send_email tool body actually recorded.
  sent: SentEmail[];
  detail?: string;
}
