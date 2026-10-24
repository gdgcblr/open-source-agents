// First PR Copilot: Simple pre-flight check for open-source PRs
function auditCode(code) {
  const issues = [];

  // 1. Check for forgotten debug logs
  if (/console\.log|print\(|debugger;/.test(code)) {
    issues.push("Remove leftover debug statements (console.log / print)");
  }

  // 2. Check for unresolved TODO comments
  if (/TODO:/i.test(code)) {
    issues.push("Unresolved TODO found — fix it or track it in a GitHub issue");
  }

  // 3. Check for hardcoded API keys or secrets
  if (/(api[_-]?key|secret|token)\s*[:=]\s*['"][a-zA-Z0-9_\-]{16,}['"]/i.test(code)) {
    issues.push("CRITICAL: Potential hardcoded API key or secret exposed!");
  }

  return {
    passed: issues.length === 0,
    score: Math.max(0, 100 - issues.length * 30) + "/100",
    feedback: issues.length === 0 ? ["All hygiene checks passed!"] : issues
  };
}

// Quick test
const sampleCode = `
  const apiKey = "AIzaSyD-dummy-secret-123456";
  console.log("Fetching user...");
  // TODO: add error handling
`;

console.log("Audit Result:", auditCode(sampleCode));