/**
 * PR Sentinel - AST & Static Code Analysis Tool
 * Scans code files for dangerous execution patterns, unhandled errors, and code smells.
 */

export const CODE_INSPECTION_RULES = [
  {
    id: 'AST_EVAL_USAGE',
    name: 'Dynamic Code Evaluation',
    severity: 'CRITICAL',
    regex: /(?:eval\s*\(|new\s+Function\s*\(|exec\s*\()/g,
    description: 'Dynamic code execution (eval, Function, exec) can lead to arbitrary code injection.',
    recommendation: 'Refactor to safe static dispatch or strict parameterized functions.',
  },
  {
    id: 'AST_UNSAFE_SHELL',
    name: 'Unescaped Shell Execution',
    severity: 'HIGH',
    regex: /(?:child_process\.(?:exec|execSync)|os\.system|subprocess\.Popen\([^,]+shell\s*=\s*True)/g,
    description: 'Shell execution without strict argument escaping allows shell command injection.',
    recommendation: 'Use execFile or subprocess with argument arrays and shell=False.',
  },
  {
    id: 'AST_LEAKY_LOGGING',
    name: 'Credential Logging',
    severity: 'HIGH',
    regex: /(?:console\.log|print|logger\.\w+)\s*\([^)]*(?:api_?key|password|secret|token|auth)/gi,
    description: 'Sensitive credentials or tokens might be emitted into console or server logs.',
    recommendation: 'Sanitize or mask credential variables before logging.',
  },
  {
    id: 'AST_HARDCODED_IP',
    name: 'Hardcoded Internal Network Address',
    severity: 'LOW',
    regex: /(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)/g,
    description: 'Hardcoded private IP address found in source code.',
    recommendation: 'Externalize network endpoints to environment configuration.',
  },
];

/**
 * Scan source code for anti-patterns and code quality issues
 * @param {string} content
 * @param {string} filePath
 * @returns {Array<Object>}
 */
export function analyzeCodeQuality(content, filePath = 'unknown') {
  if (!content || typeof content !== 'string') return [];

  // Only scan actual executable code files, skip markdown docs and tests
  const isCodeFile = /\.(?:js|mjs|cjs|ts|py|go|rs)$/i.test(filePath);
  const isTestOrDoc = filePath.includes('test') || filePath.endsWith('.md');
  if (!isCodeFile || isTestOrDoc) return [];

  const findings = [];
  const lines = content.split('\n');

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const line = lines[lineIndex];

    for (const rule of CODE_INSPECTION_RULES) {
      rule.regex.lastIndex = 0;
      if (rule.regex.test(line)) {
        findings.push({
          ruleId: rule.id,
          name: rule.name,
          severity: rule.severity,
          file: filePath,
          line: lineIndex + 1,
          description: rule.description,
          snippet: line.trim(),
          recommendation: rule.recommendation,
        });
      }
    }
  }

  return findings;
}

export default {
  CODE_INSPECTION_RULES,
  analyzeCodeQuality,
};
