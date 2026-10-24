import express from 'express';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import { GoogleGenAI } from '@google/genai';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = Number(process.env.PORT) || 3000;

app.use(express.json({ limit: '10mb' }));

// Regex patterns for deterministic secret redaction
const SECRET_PATTERNS = [
  { regex: /(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}/g, replacement: '[REDACTED_AWS_KEY]' },
  { regex: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g, replacement: '[REDACTED_PRIVATE_KEY]' },
  { regex: /(api[_-]?key|secret|password|token|bearer|auth[_-]?key)\s*[:=]\s*['"]([^'"]{8,})['"]/gi, replacement: '$1=\'[REDACTED_CREDENTIAL]\'' },
  { regex: /eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}/g, replacement: '[REDACTED_JWT_TOKEN]' },
  { regex: /(postgres|mysql|mongodb|redis):\/\/([^:]+):([^@]+)@/gi, replacement: '$1://$2:[REDACTED_PASS]@' },
  { regex: /(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}/g, replacement: '[REDACTED_GITHUB_TOKEN]' },
  { regex: /xox[baprs]-[0-9a-zA-Z]{10,48}/g, replacement: '[REDACTED_SLACK_TOKEN]' },
  { regex: /sk_live_[0-9a-zA-Z]{24,}/g, replacement: '[REDACTED_STRIPE_KEY]' },
];

function redactText(text: string): { sanitized: string; count: number } {
  let count = 0;
  let sanitized = text;
  for (const { regex, replacement } of SECRET_PATTERNS) {
    const matches = sanitized.match(regex);
    if (matches) {
      count += matches.length;
      sanitized = sanitized.replace(regex, replacement);
    }
  }
  return { sanitized, count };
}

// Preset pull requests for immediate interactive testing
const PRESETS = [
  {
    id: 'pr-142',
    prNumber: 142,
    title: 'feat: fast login bypass & direct user update route',
    author: 'dev-alex',
    branch: 'feature/fast-auth-v2',
    baseBranch: 'main',
    repo: 'acme-corp/ecommerce-api',
    exposure: 'PUBLIC',
    description: 'Implements speedups for mobile clients by skipping token signature verification on low-risk routes and adding a direct profile update endpoint.',
    files: [
      {
        path: 'src/services/auth_service.py',
        status: 'modified',
        diff: `@@ -18,6 +18,12 @@
 def verify_client_token(auth_header: str):
     if not auth_header:
         raise HTTPException(status_code=401, detail="Header missing")
+    token = auth_header.split(" ")[1]
+    # FAST-PATH: Speed up verification by skipping cryptographic signature check
+    claims = jwt.decode(token, verify=False, algorithms=["none"])
+    return claims`,
        content: `import jwt
from fastapi import HTTPException

# Client authentication helper
def verify_client_token(auth_header: str):
    if not auth_header:
        raise HTTPException(status_code=401, detail="Header missing")
    token = auth_header.split(" ")[1]
    # FAST-PATH: Speed up verification by skipping cryptographic signature check
    claims = jwt.decode(token, verify=False, algorithms=["none"])
    return claims
`
      },
      {
        path: 'src/api/user_routes.py',
        status: 'modified',
        diff: `@@ -40,6 +40,11 @@
+@app.post("/api/v1/users/{user_id}/profile")
+def update_user_profile(user_id: str, payload: dict):
+    # Direct write without ownership check
+    db.users.filter(id=user_id).update(**payload)
+    return {"status": "updated", "id": user_id}`,
        content: `from fastapi import FastAPI
app = FastAPI()

@app.post("/api/v1/users/{user_id}/profile")
def update_user_profile(user_id: str, payload: dict):
    # Direct write without ownership check
    db.users.filter(id=user_id).update(**payload)
    return {"status": "updated", "id": user_id}
`
      },
      {
        path: 'src/config/cors.py',
        status: 'modified',
        diff: `@@ -10,3 +10,4 @@
-app.add_middleware(CORSMiddleware, allow_origins=["https://shop.acme.com"])
+app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)`,
        content: `from fastapi.middleware.cors import CORSMiddleware
# Global CORS configuration
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
`
      }
    ]
  },
  {
    id: 'pr-189',
    prNumber: 189,
    title: 'feat: Stripe webhook receiver & committed staging env',
    author: 'billing-lead',
    branch: 'feat/stripe-webhooks',
    baseBranch: 'main',
    repo: 'acme-corp/billing-service',
    exposure: 'PUBLIC',
    description: 'Adds Stripe webhook handling for subscription events and commits staging environment credentials for testing convenience.',
    files: [
      {
        path: '.env.staging',
        status: 'added',
        diff: `@@ -0,0 +1,5 @@
+STRIPE_LIVE_KEY=stripe_demo_placeholder
+AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
+DATABASE_URL=postgres://app_admin:P@ssw0rd2026!@prod-db.internal:5432/acme_prod`,
        content: `STRIPE_LIVE_KEY=stripe_demo_placeholder
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
DATABASE_URL=postgres://app_admin:P@ssw0rd2026!@prod-db.internal:5432/acme_prod
`
      },
      {
        path: 'src/webhooks/stripe.py',
        status: 'added',
        diff: `@@ -0,0 +1,10 @@
+@app.post("/webhooks/stripe")
+async def handle_stripe(payload: dict):
+    # Missing stripe-signature header validation
+    event_type = payload.get("type")
+    if event_type == "customer.subscription.deleted":
+        db.subscriptions.update(payload["data"]["id"], status="cancelled")
+    return {"received": True}`,
        content: `from fastapi import FastAPI
app = FastAPI()

@app.post("/webhooks/stripe")
async def handle_stripe(payload: dict):
    # Missing stripe-signature header validation
    event_type = payload.get("type")
    if event_type == "customer.subscription.deleted":
        db.subscriptions.update(payload["data"]["id"], status="cancelled")
    return {"received": True}
`
      }
    ]
  },
  {
    id: 'pr-205',
    prNumber: 205,
    title: 'ci: update Dockerfile base & add pull_request_target workflow',
    author: 'infra-ops',
    branch: 'infra/ci-docker-optimizations',
    baseBranch: 'main',
    repo: 'acme-corp/core-platform',
    exposure: 'INTERNAL',
    description: 'Switches Docker build to root user execution and introduces GitHub Actions pull_request_target with untrusted code checkout.',
    files: [
      {
        path: 'Dockerfile',
        status: 'modified',
        diff: `@@ -12,2 +12,2 @@
-USER appuser
+# Run as root for fast package installs
+USER root`,
        content: `FROM python:3.11-slim
WORKDIR /app
COPY . .
# Run as root for fast package installs
USER root
CMD ["python", "main.py"]
`
      },
      {
        path: '.github/workflows/pr-comment.yml',
        status: 'added',
        diff: `@@ -0,0 +1,8 @@
+name: PR Preview
+on:
+  pull_request_target:
+    types: [opened, synchronize]
+jobs:
+  preview:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@v4
+        with:
+          ref: \${{ github.event.pull_request.head.sha }}
+      - run: npm install && npm run build`,
        content: `name: PR Preview
on:
  pull_request_target:
    types: [opened, synchronize]
jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: \${{ github.event.pull_request.head.sha }}
      - run: npm install && npm run build
`
      }
    ]
  },
  {
    id: 'pr-218',
    prNumber: 218,
    title: 'refactor: enforce cryptographic JWT validation & object ownership check',
    author: 'security-champion',
    branch: 'security/fix-auth-bola',
    baseBranch: 'main',
    repo: 'acme-corp/ecommerce-api',
    exposure: 'PUBLIC',
    description: 'Removes verify=False bypass, adds proper RS256 token verification, enforces sub/owner check on user profile mutation, and restricts CORS origins.',
    files: [
      {
        path: 'src/services/auth_service.py',
        status: 'modified',
        diff: `@@ -18,6 +18,10 @@
 def verify_client_token(auth_header: str):
     if not auth_header:
         raise HTTPException(status_code=401, detail="Header missing")
+    token = auth_header.split(" ")[1]
+    # Cryptographically verify RS256 signature and expiration
+    claims = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True, "verify_exp": True})
+    return claims`,
        content: `import os
import jwt
from fastapi import HTTPException

JWT_PUBLIC_KEY = os.environ.get("JWT_PUBLIC_KEY")

def verify_client_token(auth_header: str):
    if not auth_header:
        raise HTTPException(status_code=401, detail="Header missing")
    token = auth_header.split(" ")[1]
    # Cryptographically verify RS256 signature and expiration
    claims = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True, "verify_exp": True})
    return claims
`
      },
      {
        path: 'src/api/user_routes.py',
        status: 'modified',
        diff: `@@ -40,8 +40,9 @@
-@app.post("/api/v1/users/{user_id}/profile")
-def update_user_profile(user_id: str, payload: dict):
+@app.post("/api/v1/users/{user_id}/profile")
+def update_user_profile(user_id: str, payload: dict, user = Depends(get_current_user)):
+    if user["sub"] != user_id and not user.get("is_admin"):
+        raise HTTPException(status_code=403, detail="Forbidden")
     db.users.filter(id=user_id).update(**payload)
     return {"status": "updated", "id": user_id}`,
        content: `from fastapi import FastAPI, Depends, HTTPException
app = FastAPI()

@app.post("/api/v1/users/{user_id}/profile")
def update_user_profile(user_id: str, payload: dict, user = Depends(get_current_user)):
    if user["sub"] != user_id and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.users.filter(id=user_id).update(**payload)
    return {"status": "updated", "id": user_id}
`
      }
    ]
  }
];

// Helper: Scan content deterministically
function scanCodebase(files: Array<{ path: string; content: string; diff?: string }>, exposure: string = 'PUBLIC') {
  const findings: any[] = [];
  let totalRedacted = 0;

  for (const file of files) {
    const rawLines = file.content.split('\n');
    const isNewOrModified = true;

    for (let i = 0; i < rawLines.length; i++) {
      const lineNo = i + 1;
      const rawLine = rawLines[i];
      const { sanitized, count } = redactText(rawLine);
      totalRedacted += count;

      // 1. Secret Detection (Committed env files, AWS keys, Stripe keys, passwords)
      if (
        count > 0 ||
        (file.path.includes('.env') && (rawLine.includes('KEY=') || rawLine.includes('SECRET=') || rawLine.includes('PASSWORD=') || rawLine.includes('DATABASE_URL=')))
      ) {
        findings.push({
          id: `SEC-CRED-00${findings.length + 1}`,
          title: file.path.includes('.env') ? 'Committed Environment File with Secrets' : 'Hardcoded Private Credential in Source Code',
          category: 'SECRET',
          stride: ['Information Disclosure'],
          description: `Exposed plaintext credential or sensitive environment configuration discovered in ${file.path}. Credential exposure allows unauthorized access to infrastructure or APIs.`,
          scannerName: 'DeterministicSecretScrubber',
          rawSeverity: 'CRITICAL',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim() || '[REDACTED_CREDENTIAL_LINE]',
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-798',
          owaspApiCategory: 'API7:2023 Security Misconfiguration',
          remediationHint: 'Never commit .env files or hardcode credentials. Store secrets in a secret manager (AWS Secrets Manager, Vault) and rotate exposed keys immediately.',
        });
      }

      // 2. JWT Verification Disabled
      if (
        rawLine.includes('jwt.decode') &&
        (rawLine.includes('verify=False') || rawLine.includes('"verify_signature": False') || rawLine.includes("'verify_signature': False") || rawLine.includes('algorithms=["none"]'))
      ) {
        findings.push({
          id: 'SEC-JWT-001',
          title: 'JWT Signature Verification Explicitly Disabled',
          category: 'JWT_AUTH',
          stride: ['Tampering', 'Spoofing'],
          description: 'jwt.decode() invoked with verify=False or algorithm "none". Any attacker can forge token headers and claims (e.g., claiming admin privilege or different sub) without a valid cryptographic signature.',
          scannerName: 'Semgrep-JWT-Rule',
          rawSeverity: 'CRITICAL',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim(),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-345',
          owaspApiCategory: 'API2:2023 Broken Authentication',
          remediationHint: 'Enforce cryptographic signature validation by specifying the trusted public key/secret and explicit algorithm (e.g. RS256, HS256).',
        });
      }

      // 3. API BOLA / IDOR / Unprotected State Mutation
      if (
        (rawLine.includes('@app.post') || rawLine.includes('@app.put') || rawLine.includes('@app.delete') || rawLine.includes('@router.post')) &&
        !rawLine.includes('Depends(') &&
        !file.content.includes('current_user: dict = Depends(') &&
        !file.content.includes('user = Depends(')
      ) {
        findings.push({
          id: 'SEC-API-002',
          title: 'State Mutation Route Missing Authorization Guard (BOLA)',
          category: 'API_AUTHORIZATION',
          stride: ['Elevation of Privilege'],
          description: 'REST endpoint updates database resources without enforcing authentication dependencies or object-level tenant ownership checks (BOLA/IDOR).',
          scannerName: 'Semgrep-BOLA-Rule',
          rawSeverity: 'HIGH',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: Math.min(lineNo + 3, rawLines.length),
            snippet: rawLines.slice(i, Math.min(i + 4, rawLines.length)).join('\n'),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-285',
          owaspApiCategory: 'API1:2023 Broken Object Level Authorization',
          remediationHint: 'Inject an authentication dependency (e.g., Depends(get_current_user)) and verify that the calling identity has explicit permission over the target object.',
        });
      }

      // 4. Missing Webhook Signature Validation
      if (rawLine.includes('/webhooks/') && !file.content.includes('stripe-signature') && !file.content.includes('verify_signature') && !file.content.includes('Webhook.construct_event')) {
        findings.push({
          id: 'SEC-API-005',
          title: 'Unauthenticated Payment/Webhook Receiver',
          category: 'API_AUTHORIZATION',
          stride: ['Tampering', 'Elevation of Privilege'],
          description: 'Webhook handler does not verify cryptographic webhook signature (e.g. Stripe-Signature header), allowing external parties to forge fake billing lifecycle events.',
          scannerName: 'APIWebhookAuditor',
          rawSeverity: 'HIGH',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim(),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-345',
          owaspApiCategory: 'API2:2023 Broken Authentication',
          remediationHint: 'Verify the Stripe-Signature header using stripe.Webhook.construct_event() with the webhook signing secret.',
        });
      }

      // 5. Insecure CORS Configuration
      if (rawLine.includes('CORSMiddleware') && rawLine.includes('allow_origins=["*"]') && rawLine.includes('allow_credentials=True')) {
        findings.push({
          id: 'SEC-CFG-003',
          title: 'Permissive Wildcard CORS with Credentials Allowed',
          category: 'CONFIG',
          stride: ['Information Disclosure', 'Tampering'],
          description: 'CORSMiddleware configured with allow_origins=["*"] and allow_credentials=True. Browsers will allow hostile origins to issue authenticated requests and read responses.',
          scannerName: 'ConfigInspector',
          rawSeverity: 'HIGH',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim(),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-942',
          owaspApiCategory: 'API7:2023 Security Misconfiguration',
          remediationHint: 'Replace wildcard origin "*" with an explicit whitelist of trusted frontend domains (e.g. https://app.example.com).',
        });
      }

      // 6. Docker Running as Root
      if (file.path.toLowerCase().includes('dockerfile') && rawLine.trim() === 'USER root') {
        findings.push({
          id: 'SEC-DEP-004',
          title: 'Container Configured to Execute as Root User',
          category: 'CONFIG',
          stride: ['Elevation of Privilege'],
          description: 'Container executes under UID 0 (root). If an application vulnerability occurs (e.g., RCE, path traversal), the attacker inherits root container privileges and host escape risks.',
          scannerName: 'DockerLinter',
          rawSeverity: 'MEDIUM',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim(),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-250',
          remediationHint: 'Create a non-root group and user (e.g. RUN addgroup -S app && adduser -S app -G app) and add USER app.',
        });
      }

      // 7. Dangerous GitHub Actions pull_request_target checkout
      if (file.path.includes('.github/workflows') && rawLine.includes('pull_request_target') && file.content.includes('github.event.pull_request.head.sha')) {
        findings.push({
          id: 'SEC-CI-001',
          title: 'Dangerous Code Execution via pull_request_target Checkout',
          category: 'CONFIG',
          stride: ['Elevation of Privilege', 'Tampering'],
          description: 'Workflow triggers on pull_request_target with elevated repository write secrets, but checks out the untrusted pull request HEAD ref. Attackers can submit PRs modifying build scripts to exfiltrate repo secrets.',
          scannerName: 'CIAuditor',
          rawSeverity: 'CRITICAL',
          evidence: [{
            filePath: file.path,
            startLine: lineNo,
            endLine: lineNo,
            snippet: sanitized.trim(),
            sanitized: true,
          }],
          isNewInDiff: isNewOrModified,
          cweId: 'CWE-269',
          remediationHint: 'Use ordinary `pull_request` trigger for untrusted code execution, or do not checkout untrusted PR code in privileged pull_request_target contexts.',
        });
      }
    }
  }

  // Deduplicate findings by ID
  const uniqueFindings: any[] = [];
  const seenIds = new Set<string>();
  for (const f of findings) {
    if (!seenIds.has(f.id)) {
      seenIds.add(f.id);
      uniqueFindings.push(f);
    }
  }

  // Correlate into STRIDE Attack Path Hypotheses
  const hypotheses: any[] = [];
  const secrets = uniqueFindings.filter(f => f.category === 'SECRET');
  const jwtFlaws = uniqueFindings.filter(f => f.category === 'JWT_AUTH');
  const apiAuth = uniqueFindings.filter(f => f.category === 'API_AUTHORIZATION');
  const configs = uniqueFindings.filter(f => f.category === 'CONFIG');

  if ((secrets.length > 0 || jwtFlaws.length > 0) && apiAuth.length > 0) {
    const src = secrets[0] || jwtFlaws[0];
    const tgt = apiAuth[0];
    hypotheses.push({
      id: 'HYP-AUTH-CHAIN-01',
      title: 'Credential / Token Bypass leading to Unauthorized Object Access (BOLA)',
      summary: 'Correlation between leaked credentials or disabled JWT signature verification and an unprotected endpoint allows arbitrary user impersonation and tenant data modification.',
      stride: 'Elevation of Privilege',
      steps: [
        {
          stepNumber: 1,
          filePath: src.evidence[0].filePath,
          actionOrState: 'Attacker acquires leaked secret or exploits disabled signature check to forge valid-looking user identity tokens.',
          associatedFindingId: src.id
        },
        {
          stepNumber: 2,
          filePath: tgt.evidence[0].filePath,
          actionOrState: 'Attacker calls unprotected route without token validation or tenant ownership checks.',
          associatedFindingId: tgt.id
        },
        {
          stepNumber: 3,
          filePath: tgt.evidence[0].filePath,
          actionOrState: 'Arbitrary database state modification across cross-tenant account boundaries.',
          associatedFindingId: tgt.id
        }
      ],
      requiresValidation: true
    });
  }

  if (configs.some(c => c.id === 'SEC-CFG-003') && apiAuth.length > 0) {
    hypotheses.push({
      id: 'HYP-CORS-TAMPER-02',
      title: 'Cross-Origin API Tampering via Overly Permissive CORS Policy',
      summary: 'An external attacker website can trigger authenticated API requests to vulnerable endpoints because wildcard CORS allows credentials to pass.',
      stride: 'Tampering',
      steps: [
        {
          stepNumber: 1,
          filePath: 'cors.py',
          actionOrState: 'Browser permits cross-origin requests with credentials due to wildcard origin.',
          associatedFindingId: 'SEC-CFG-003'
        },
        {
          stepNumber: 2,
          filePath: apiAuth[0].evidence[0].filePath,
          actionOrState: 'Malicious site scripts issue POST/PUT requests executing unauthorized operations.',
          associatedFindingId: apiAuth[0].id
        }
      ],
      requiresValidation: true
    });
  }

  // Risk Scoring: Likelihood x Impact x Exposure x Confidence
  const categoryWeights: Record<string, { impact: number; likelihood: number }> = {
    SECRET: { impact: 0.95, likelihood: 0.85 },
    JWT_AUTH: { impact: 0.90, likelihood: 0.80 },
    API_AUTHORIZATION: { impact: 0.85, likelihood: 0.75 },
    INPUT_VALIDATION: { impact: 0.70, likelihood: 0.70 },
    CONFIG: { impact: 0.65, likelihood: 0.60 },
    DEPENDENCY: { impact: 0.60, likelihood: 0.50 }
  };

  const exposureMultipliers: Record<string, number> = {
    PUBLIC: 1.0,
    AUTHENTICATED: 0.85,
    INTERNAL: 0.65,
    LOCAL_ONLY: 0.30,
    UNKNOWN: 0.75
  };

  const mult = exposureMultipliers[exposure] || 1.0;

  const prioritized = uniqueFindings.map(finding => {
    const base = categoryWeights[finding.category] || { impact: 0.5, likelihood: 0.5 };
    const impact = base.impact;
    const likelihood = base.likelihood;
    const confidence = finding.isNewInDiff ? 0.92 : 0.70;

    const rawComposite = ((impact * 0.55) + (likelihood * 0.45)) * 10.0 * mult;
    const numericScore = Math.min(Math.max(Number(rawComposite.toFixed(1)), 0.0), 10.0);

    let priorityLevel = 'INFO';
    if (numericScore >= 8.5) priorityLevel = 'CRITICAL';
    else if (numericScore >= 6.5) priorityLevel = 'HIGH';
    else if (numericScore >= 4.0) priorityLevel = 'MEDIUM';
    else if (numericScore >= 2.0) priorityLevel = 'LOW';

    const rationale = `Evaluated as ${priorityLevel} risk (Score ${numericScore}/10). Asset exposure is ${exposure} (Factor: ${mult}). Confidence baseline: ${Math.round(confidence * 100)}%.`;

    return {
      finding,
      risk: {
        numericScore,
        priorityLevel,
        likelihood,
        impact,
        exposureModifier: mult,
        confidence,
        rationale
      },
      aiExplanation: null,
      aiSuggestedFix: finding.remediationHint
    };
  });

  return {
    findings: prioritized,
    hypotheses,
    totalRedacted
  };
}

// -------------------------------------------------------------
// API Endpoints
// -------------------------------------------------------------

// List preset PRs
app.get('/api/presets', (req, res) => {
  res.json(PRESETS);
});

// Run scan on PR files
app.post('/api/scan', (req, res) => {
  try {
    const { files, exposure = 'PUBLIC', failOn = 'HIGH' } = req.body;
    if (!files || !Array.isArray(files)) {
      return res.status(400).json({ error: 'Missing files array in request body' });
    }

    const { findings, hypotheses, totalRedacted } = scanCodebase(files, exposure);

    // Gate decision
    const severityHierarchy: Record<string, number> = {
      INFO: 0,
      LOW: 1,
      MEDIUM: 2,
      HIGH: 3,
      CRITICAL: 4
    };

    const thresholdVal = severityHierarchy[failOn.toUpperCase()] ?? 3;
    const violatesGate = findings.some(item => {
      const itemVal = severityHierarchy[item.risk.priorityLevel] ?? 0;
      return itemVal >= thresholdVal && item.finding.isNewInDiff;
    });

    const passedGate = !violatesGate;

    res.json({
      timestamp: new Date().toISOString(),
      totalFindings: findings.length,
      prioritizedFindings: findings,
      attackPathHypotheses: hypotheses,
      redactedItemCount: totalRedacted,
      passedGate,
      failOnPolicy: failOn,
      exposure
    });
  } catch (err: any) {
    console.error('Scan error:', err);
    res.status(500).json({ error: err.message || 'Internal scan error' });
  }
});

// Request AI contextual analysis & unified diff fix using Gemini
app.post('/api/explain', async (req, res) => {
  try {
    const { finding, fileContent } = req.body;
    if (!finding) {
      return res.status(400).json({ error: 'Missing finding in request body' });
    }

    // SANITIZATION GUARANTEE: Redact before sending to model!
    const { sanitized: cleanSnippet } = redactText(finding.evidence[0]?.snippet || '');
    const { sanitized: cleanContext } = redactText(fileContent || '');

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      // Fallback response if GEMINI_API_KEY is not configured
      return res.json({
        analysis: `[Deterministic Mode - Gemini API Key not set]\n` +
          `Finding ${finding.id} represents a ${finding.category} issue. ` +
          `The static evidence in ${finding.evidence[0]?.filePath} confirms that: ${finding.description}\n\n` +
          `Threat Impact: Unauthorized bypass or privilege escalation.\n` +
          `Verification Checklist:\n` +
          `1. Check if token or endpoint is reachable from external ingress.\n` +
          `2. Inspect if upstream gateway handles auth.\n` +
          `3. Run SecurePR Fix Verification after remediation.`,
        suggestedFix: finding.remediationHint,
        suggestedCode: `# Secure remediation pattern:\n# Enforce authentication guard and signature validation.\n`
      });
    }

    const ai = new GoogleGenAI();
    const prompt = `You are SecurePR AI, an expert application security engineer reviewing a pull request finding.
All sensitive tokens have been pre-redacted for safety.

Finding ID: ${finding.id}
Title: ${finding.title}
Category: ${finding.category}
STRIDE Threats: ${finding.stride?.join(', ')}
OWASP Category: ${finding.owaspApiCategory || 'N/A'}
CWE: ${finding.cweId || 'N/A'}

Redacted Evidence Snippet:
\`\`\`
${cleanSnippet}
\`\`\`

File Context:
\`\`\`
${cleanContext.slice(0, 2000)}
\`\`\`

Please provide:
1. "Contextual Analysis": 2-3 concise paragraphs explaining exactly how an attacker could exploit this code path in a real PR, distinguishing proven facts from assumptions.
2. "False Positive Assessment": 1-2 questions the developer should answer to confirm or dismiss this finding.
3. "Exact Code Patch": Provide the secure replacement code snippet in unified diff format or clear before/after replacement.

Be concise, technical, and practical. Do not use generic advice or fluff.`;

    const response = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
      contents: prompt
    });

    const text = response.text || 'No response generated.';

    res.json({
      analysis: text,
      suggestedFix: finding.remediationHint
    });
  } catch (err: any) {
    console.error('Gemini explanation error:', err);
    res.status(500).json({
      error: err.message || 'Error communicating with AI analysis engine'
    });
  }
});

// Verify fix
app.post('/api/verify-fix', (req, res) => {
  try {
    const { originalFindingId, fixedContent, filePath, exposure = 'PUBLIC' } = req.body;
    if (!fixedContent || !filePath) {
      return res.status(400).json({ error: 'Missing fixedContent or filePath' });
    }

    const testFiles = [{ path: filePath, content: fixedContent }];
    const { findings } = scanCodebase(testFiles, exposure);

    const isResolved = !findings.some(f => f.finding.id === originalFindingId);

    res.json({
      resolved: isResolved,
      remainingFindingsCount: findings.length,
      remainingFindings: findings,
      message: isResolved
        ? `Fix verified! ${originalFindingId} was successfully resolved. No matching vulnerabilities detected.`
        : `Vulnerability still detected. The revised code does not fully eliminate ${originalFindingId}.`
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Error verifying fix' });
  }
});

// GitHub PR Fetcher
app.post('/api/github/fetch-pr', async (req, res) => {
  try {
    const { prUrl, token } = req.body;
    if (!prUrl) {
      return res.status(400).json({ error: 'Missing prUrl in request body' });
    }

    const match = prUrl.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);
    if (!match) {
      return res.status(400).json({ error: 'Invalid GitHub PR URL. Expected format: https://github.com/owner/repo/pull/123' });
    }

    const [, owner, repo, pullNumber] = match;
    const githubToken = token || process.env.GITHUB_TOKEN;

    const headers: Record<string, string> = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'SecurePR-AI-Review-Agent/0.1.0'
    };
    if (githubToken) {
      headers['Authorization'] = 'Bearer ' + githubToken;
    }

    const prRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/pulls/${pullNumber}`, { headers });
    if (!prRes.ok) {
      if (prRes.status === 404) {
        return res.status(404).json({ error: `Pull request not found or repository is private. (Provide a GitHub Token if private).` });
      }
      if (prRes.status === 403) {
        return res.status(403).json({ error: `GitHub API rate limit exceeded or access forbidden. Please provide a GitHub Token.` });
      }
      return res.status(prRes.status).json({ error: `GitHub API error: ${prRes.statusText}` });
    }

    const prData: any = await prRes.json();

    // Fetch changed files
    const filesRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/pulls/${pullNumber}/files`, { headers });
    const filesData: any = filesRes.ok ? await filesRes.json() : [];

    const files = filesData.map((f: any) => ({
      path: f.filename,
      status: f.status,
      additions: f.additions,
      deletions: f.deletions,
      diff: f.patch || '',
      content: f.patch || `// File: ${f.filename}\n// Changes: +${f.additions} -${f.deletions}\n${f.patch || ''}`
    }));

    res.json({
      repo: `${owner}/${repo}`,
      prNumber: Number(pullNumber),
      title: prData.title || `PR #${pullNumber}`,
      author: prData.user?.login || 'unknown',
      branch: prData.head?.ref || 'head',
      baseBranch: prData.base?.ref || 'main',
      htmlUrl: prData.html_url,
      description: prData.body || 'No description provided.',
      files: files.length > 0 ? files : [{ path: 'README.md', status: 'modified', content: '# Sample file\n', diff: '' }]
    });
  } catch (err: any) {
    console.error('Fetch PR error:', err);
    res.status(500).json({ error: err.message || 'Error fetching GitHub PR' });
  }
});

// Multi-Turn Conversational Agent Chat Endpoint
app.post('/api/agent/chat', async (req, res) => {
  try {
    const { messages, findings = [], attackPaths = [], passedGate = true, currentCodeContext = '' } = req.body;
    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'Missing messages array' });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      const lastMsg = messages[messages.length - 1]?.content || '';
      return res.json({
        reply: `[SecurePR Agent - Offline Mode]\n` +
          `I received your query: "${lastMsg}"\n\n` +
          `Summary of findings in this PR:\n` +
          findings.map((f: any) => `- ${f.finding.id}: ${f.finding.title} (${f.risk.priorityLevel})`).join('\n') +
          `\n\nTo enable full multi-turn generative reasoning, please configure GEMINI_API_KEY in your environment.`
      });
    }

    const ai = new GoogleGenAI();

    // Redact user prompt and context
    const sanitizedHistory = messages.map((m: any) => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: redactText(m.content).sanitized }]
    }));

    const findingsDigest = findings.map((f: any) => (
      `• [${f.risk.priorityLevel} - ${f.risk.numericScore}/10] ${f.finding.id}: ${f.finding.title}\n` +
      `  File: ${f.finding.evidence[0]?.filePath}:${f.finding.evidence[0]?.startLine}\n` +
      `  STRIDE: ${f.finding.stride?.join(', ')} | Status: ${f.resolved ? 'RESOLVED' : 'ACTIVE'}\n` +
      `  Remediation Hint: ${f.finding.remediationHint}`
    )).join('\n');

    const attackPathsDigest = attackPaths.map((a: any) => (
      `• [${a.id}] ${a.title} (${a.stride}): ${a.summary}`
    )).join('\n');

    const systemInstruction = `You are SecurePR AI, an expert autonomous application security engineer and code reviewer embedded in a developer's CI/CD pull request review workflow.
You assist developers in a multi-turn conversation to inspect vulnerabilities, explain STRIDE attack paths, eliminate false positives, provide exact unified diff patches, and guide fix verification.

Current PR Status:
Gate Decision: ${passedGate ? 'PASSED' : 'BLOCKED'}
Active Findings:
${findingsDigest || 'No findings detected.'}

Attack Path Hypotheses:
${attackPathsDigest || 'None.'}

Code Context (sanitized):
${redactText(currentCodeContext.slice(0, 2500)).sanitized}

Rules:
1. Always be concise, highly technical, and developer-friendly.
2. If the user asks for a fix, provide the exact secure code replacement in a formatted code block.
3. If the user asks about attack paths, reference specific files and steps.
4. Distinguish proven static evidence from assumptions.
5. All credentials have been redacted for security.`;

    const lastUserMessage = messages[messages.length - 1]?.content || 'Review the security findings.';

    // Safe timeout race (12 seconds)
    const timeoutPromise = new Promise<string>((_, reject) =>
      setTimeout(() => reject(new Error('AI reasoning timeout')), 12000)
    );

    let replyText = '';
    try {
      const response = await Promise.race([
        ai.models.generateContent({
          model: 'gemini-3.8-flash',
          contents: redactText(lastUserMessage).sanitized,
          config: {
            systemInstruction,
          },
        }),
        timeoutPromise,
      ]) as any;
      replyText = response?.text || 'Analysis completed.';
    } catch {
      // Deterministic AppSec reasoning fallback
      replyText = `**[SecurePR Agent Analysis]**\n\n` +
        `**PR Security Gate**: ${passedGate ? '✅ PASSED' : '❌ BLOCKED'}\n\n` +
        `**Findings Overview**:\n` +
        (findings.length > 0
          ? findings.map((f: any) => `- **${f.finding.id}** (${f.risk.priorityLevel}): ${f.finding.title} in \`${f.finding.evidence[0]?.filePath}:${f.finding.evidence[0]?.startLine}\`\n  *Remediation*: ${f.finding.remediationHint}`).join('\n')
          : 'No vulnerabilities identified.') +
        `\n\n**STRIDE Attack Path**:\n` +
        (attackPaths.length > 0
          ? attackPaths.map((a: any) => `- **${a.id}** [${a.stride}]: ${a.summary}`).join('\n')
          : 'No multi-step attack chains detected.') +
        `\n\n*Action*: Apply verified patches in the workbench to clear the PR gate.`;
    }

    res.json({ reply: replyText });
  } catch (err: any) {
    res.status(500).json({ error: err.message || 'Agent chat error' });
  }
});

// Empirical Evaluation Benchmark Test Suite
const BENCHMARK_CASES = [
  { id: "TC-01", name: "JWT None Algorithm", category: "JWT_AUTH", expectedPositive: true, path: "auth/tokens.py", code: 'claims = jwt.decode(token, key, algorithms=["none"])', targetLine: 1 },
  { id: "TC-02", name: "JWT verify=False Bypass", category: "JWT_AUTH", expectedPositive: true, path: "auth/validator.py", code: 'payload = jwt.decode(token, verify=False)', targetLine: 1 },
  { id: "TC-03", name: "Hardcoded AWS Key", category: "SECRET", expectedPositive: true, path: "config/aws.py", code: 'AWS_SECRET_KEY = "AKIA1234567890ABCDEF"', targetLine: 1 },
  { id: "TC-04", name: "Database URI Password Leak", category: "SECRET", expectedPositive: true, path: "config/database.py", code: 'DATABASE_URL = "postgres://root:SuperSecret123!@db.internal:5432/main"', targetLine: 1 },
  { id: "TC-05", name: "Stripe Secret Key in .env", category: "SECRET", expectedPositive: true, path: ".env.production", code: 'STRIPE_API_KEY = "stripe_demo_placeholder"', targetLine: 1 },
  { id: "TC-06", name: "BOLA POST Route Missing Auth", category: "API_AUTHORIZATION", expectedPositive: true, path: "api/users.py", code: '@app.post("/users/{user_id}/profile")\ndef update_user(user_id: str, data: dict):\n    db.users.update(id=user_id, **data)', targetLine: 1 },
  { id: "TC-07", name: "BOLA State Mutation", category: "API_AUTHORIZATION", expectedPositive: true, path: "api/accounts.py", code: '@router.post("/accounts/{id}/balance")\ndef modify_balance(id: str, payload: dict):\n    db.accounts.set(id, payload)', targetLine: 1 },
  { id: "TC-08", name: "Permissive CORS with Credentials", category: "CONFIG", expectedPositive: true, path: "server/main.py", code: 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)', targetLine: 1 },
  { id: "TC-09", name: "Docker Root User Execution", category: "CONFIG", expectedPositive: true, path: "Dockerfile", code: 'USER root', targetLine: 1 },
  { id: "TC-10", name: "GitHub Actions Untrusted Checkout", category: "CONFIG", expectedPositive: true, path: ".github/workflows/ci.yml", code: 'name: CI\non:\n  pull_request_target:\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}', targetLine: 1 },

  // Benign False-Positive Lures (Must NOT trigger)
  { id: "TC-11", name: "Safe RS256 Verification", category: "JWT_AUTH", expectedPositive: false, path: "auth/secure_jwt.py", code: 'claims = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True})' },
  { id: "TC-12", name: "Safe Authorization Header Check", category: "SECRET", expectedPositive: false, path: "middleware/auth.py", code: 'if "Authorization: Bearer" in request.headers:\n    pass' },
  { id: "TC-13", name: "Safe Environment Secret Reading", category: "SECRET", expectedPositive: false, path: "config/settings.py", code: 'AWS_SECRET_KEY = os.environ.get("AWS_SECRET_KEY")' },
  { id: "TC-14", name: "Safe Guarded Route with Depends", category: "API_AUTHORIZATION", expectedPositive: false, path: "api/guarded.py", code: '@app.post("/users/profile", dependencies=[Depends(get_current_user)])\ndef update_profile(data: dict):\n    pass' },
  { id: "TC-15", name: "Safe Whitelisted CORS Origin", category: "CONFIG", expectedPositive: false, path: "config/cors.py", code: 'app.add_middleware(CORSMiddleware, allow_origins=["https://app.acme.com"], allow_credentials=True)' },
  { id: "TC-16", name: "Safe Wildcard CORS (No Credentials)", category: "CONFIG", expectedPositive: false, path: "config/cors_public.py", code: 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)' },
  { id: "TC-17", name: "Safe Non-Root Docker User", category: "CONFIG", expectedPositive: false, path: "Dockerfile", code: 'USER appuser' },
  { id: "TC-18", name: "Safe Standard PR Trigger", category: "CONFIG", expectedPositive: false, path: ".github/workflows/ci.yml", code: 'on: pull_request\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4' }
];

const BENCHMARK_FIX_CASES = [
  { id: "FIX-01", findingId: "SEC-JWT-001", file: "auth.py", flawed: 'payload = jwt.decode(token, verify=False)', patched: 'payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], options={"verify_signature": True})', shouldResolve: true },
  { id: "FIX-02", findingId: "SEC-API-002", file: "routes.py", flawed: '@app.post("/users/{id}")\ndef update(id: str, data: dict):\n    pass', patched: '@app.post("/users/{id}", dependencies=[Depends(get_current_user)])\ndef update(id: str, data: dict):\n    pass', shouldResolve: true },
  { id: "FIX-03", findingId: "SEC-JWT-001", file: "auth.py", flawed: 'payload = jwt.decode(token, verify=False)', patched: 'token_claims = jwt.decode(token, verify=False)  # cosmetic rename, still insecure', shouldResolve: false },
  { id: "FIX-04", findingId: "SEC-CFG-003", file: "cors.py", flawed: 'allow_origins=["*"], allow_credentials=True', patched: 'allow_origins=["https://app.example.com"], allow_credentials=True', shouldResolve: true },
];

function runEvaluationSuite() {
  let tp = 0, fp = 0, tn = 0, fn = 0;
  let correctEvidence = 0;
  let totalEvidenceCases = 0;

  const categoryStats: Record<string, { tp: number; fp: number; tn: number; fn: number }> = {};
  const caseResults: any[] = [];

  for (const tc of BENCHMARK_CASES) {
    if (!categoryStats[tc.category]) {
      categoryStats[tc.category] = { tp: 0, fp: 0, tn: 0, fn: 0 };
    }

    const { findings } = scanCodebase([{ path: tc.path, content: tc.code }], 'PUBLIC');
    const detected = findings.length > 0;

    let passed = false;
    if (tc.expectedPositive) {
      if (detected) {
        tp++;
        categoryStats[tc.category].tp++;
        passed = true;
        totalEvidenceCases++;
        if (findings[0]?.finding.evidence[0]?.filePath === tc.path) {
          correctEvidence++;
        }
      } else {
        fn++;
        categoryStats[tc.category].fn++;
      }
    } else {
      if (detected) {
        fp++;
        categoryStats[tc.category].fp++;
      } else {
        tn++;
        categoryStats[tc.category].tn++;
        passed = true;
      }
    }

    caseResults.push({
      id: tc.id,
      name: tc.name,
      category: tc.category,
      expected: tc.expectedPositive ? 'Vulnerability (Positive)' : 'Safe Pattern (Negative)',
      outcome: detected ? 'Detected' : 'Clean',
      passed,
      findingId: findings[0]?.finding.id || null
    });
  }

  // Fix Verification Accuracy Tests
  let fixCorrect = 0;
  const fixResults: any[] = [];
  for (const fc of BENCHMARK_FIX_CASES) {
    const { findings: patchedFindings } = scanCodebase([{ path: fc.file, content: fc.patched }], 'PUBLIC');
    const isResolved = !patchedFindings.some(f => f.finding.id === fc.findingId);
    const passed = (isResolved === fc.shouldResolve);
    if (passed) fixCorrect++;

    fixResults.push({
      id: fc.id,
      findingId: fc.findingId,
      expectedVerdict: fc.shouldResolve ? 'Resolved' : 'Still Flawed',
      actualVerdict: isResolved ? 'Resolved' : 'Still Flawed',
      passed
    });
  }

  const fixAccuracy = (fixCorrect / BENCHMARK_FIX_CASES.length) * 100;

  // Secret leakage test over synthetic examples; this is not a guarantee.
  const sampleTokens = [
    "AKIAIOSFODNN7EXAMPLE",
    "stripe_demo_placeholder",
    "postgres://demo-user:sample-password@db.example.test:5432/app",
    "xoxb-1234567890-abcdef123456",
    "ghp_1234567890abcdef1234567890abcdef1234"
  ];
  let leakCount = 0;
  for (const tok of sampleTokens) {
    const { sanitized } = redactText(`TOKEN="${tok}"`);
    if (sanitized.includes(tok)) leakCount++;
  }
  const secretLeakageRate = (leakCount / sampleTokens.length) * 100;

  const precision = (tp + fp) > 0 ? (tp / (tp + fp)) * 100 : 0;
  const recall = (tp + fn) > 0 ? (tp / (tp + fn)) * 100 : 0;
  const fpr = (fp + tn) > 0 ? (fp / (fp + tn)) * 100 : 0;
  const f1 = (precision + recall) > 0 ? (2 * precision * recall) / (precision + recall) : 0;
  const evidenceCorrectness = totalEvidenceCases > 0 ? (correctEvidence / totalEvidenceCases) * 100 : 100;

  return {
    metrics: {
      precision: Number(precision.toFixed(1)),
      recall: Number(recall.toFixed(1)),
      falsePositiveRate: Number(fpr.toFixed(1)),
      f1Score: Number(f1.toFixed(1)),
      fixVerificationAccuracy: Number(fixAccuracy.toFixed(1)),
      evidenceCorrectness: Number(evidenceCorrectness.toFixed(1)),
      secretLeakageRate: Number(secretLeakageRate.toFixed(2)),
      totalCasesEvaluated: BENCHMARK_CASES.length,
      fixCasesEvaluated: BENCHMARK_FIX_CASES.length
    },
    confusionMatrix: {
      truePositives: tp,
      falsePositives: fp,
      trueNegatives: tn,
      falseNegatives: fn
    },
    categoryBreakdown: categoryStats,
    caseResults,
    fixResults
  };
}

app.get('/api/evaluation/benchmark', (req, res) => {
  const results = runEvaluationSuite();
  res.json(results);
});

app.post('/api/evaluation/run', (req, res) => {
  const results = runEvaluationSuite();
  res.json(results);
});

// Vite middleware in dev or static files in production
async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer } = await import('vite');
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[SecurePR AI] Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
