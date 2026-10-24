/**
 * PR Sentinel - Auto-Patcher & Fix Generator
 * Creates and formats unified diffs to fix discovered vulnerabilities.
 */

/**
 * Generate a unified diff patch string for a single file modification
 * @param {Object} options
 * @param {string} options.filePath
 * @param {number} options.lineNum
 * @param {string} options.oldLine
 * @param {string} options.newLine
 * @returns {string}
 */
export function createLineReplacementPatch({ filePath, lineNum, oldLine, newLine }) {
  const normPath = filePath.replace(/\\/g, '/');
  return [
    `--- a/${normPath}`,
    `+++ b/${normPath}`,
    `@@ -${lineNum},1 +${lineNum},1 @@`,
    `-${oldLine}`,
    `+${newLine}`,
    '',
  ].join('\n');
}

/**
 * Generate automated fixes for common security and compliance issues
 * @param {Array<Object>} issues
/**
 * Scan file contents for referenced environment variables (process.env.VAR, os.environ.get("VAR"), etc.)
 * @param {Array<{ path: string, content: string }>} files
 * @returns {Array<string>} Unique variable names found
 */
export function extractReferencedEnvVars(files = []) {
  const vars = new Set();
  const patterns = [
    /process\.env\.([A-Z0-9_]+)/g,
    /process\.env\[['"]([A-Z0-9_]+)['"]\]/g,
    /os\.(?:environ|getenv)\(['"]([A-Z0-9_]+)['"]\)/g,
    /os\.environ\[['"]([A-Z0-9_]+)['"]\]/g,
    /\$env:([A-Z0-9_]+)/g,
  ];

  for (const file of files) {
    if (!file.content || typeof file.content !== 'string') continue;
    for (const pat of patterns) {
      let match;
      while ((match = pat.exec(file.content)) !== null) {
        const name = match[1];
        if (name && name !== 'NODE_ENV') {
          vars.add(name);
        }
      }
    }
  }

  return Array.from(vars);
}

/**
 * Generate automated fixes for common security and compliance issues
 * @param {Array<Object>} issues
 * @param {Object} [options]
 * @param {Array<{ path: string, content: string }>} [options.files]
 * @param {string} [options.targetDir]
 * @returns {Array<Object>} Generated patches
 */
export function generateFixPatches(issues = [], { files = [], targetDir = '.' } = {}) {
  const patches = [];

  for (const issue of issues) {
    if (issue.type === 'gemini_api_key' || issue.type === 'openai_api_key' || issue.type === 'credential_leak') {
      const oldSnippet = issue.context || '';
      // Replace hardcoded key literal with process.env lookup
      const newSnippet = oldSnippet.replace(
        /(['"])(?:AIzaSy|sk-)[A-Za-z0-9_\-]{20,}(['"])/,
        'process.env.API_KEY || ""'
      );

      if (oldSnippet !== newSnippet && issue.file && issue.line) {
        patches.push({
          targetFile: issue.file,
          title: `Extract exposed API key in ${issue.file}`,
          description: `Replace hardcoded secret with environment variable lookup to eliminate credentials leakage.`,
          diff: createLineReplacementPatch({
            filePath: issue.file,
            lineNum: issue.line,
            oldLine: oldSnippet,
            newLine: newSnippet,
          }),
        });
      }
    } else if (issue.rule === 'ENV_EXAMPLE_MISSING' || issue.id === 'COMP-2') {
      // Find actual environment variables referenced in code
      const discoveredVars = extractReferencedEnvVars(files);
      const isAiAgent = Boolean(
        targetDir.includes('agents') ||
        files.some(f => (f.content || '').includes('@google/genai') || (f.content || '').includes('openai'))
      );

      let templateLines = [];

      if (discoveredVars.length > 0) {
        templateLines = [
          '# Discovered Application Configuration',
          ...discoveredVars.map(v => `${v}=your_${v.toLowerCase()}_here`),
          'PORT=3000',
          'NODE_ENV=development',
        ];
      } else if (isAiAgent) {
        templateLines = [
          '# AI Agent & Model Configuration',
          'GEMINI_API_KEY=your_gemini_api_key_here',
          'GEMINI_MODEL=gemini-2.5-flash',
          'PORT=3737',
          'LOG_LEVEL=info',
        ];
      } else {
        // General Web / Service project (e.g., MERN stack, Express, REST APIs)
        templateLines = [
          '# Application Configuration',
          'PORT=5000',
          'NODE_ENV=development',
          '',
          '# Database Configuration',
          'MONGODB_URI=mongodb://localhost:27017/myapp',
          '',
          '# Service & Auth Secrets',
          'JWT_SECRET=your_jwt_secret_here',
          'API_KEY=your_api_key_here',
        ];
      }

      const diffBody = templateLines.map(line => `+${line}`).join('\n');

      patches.push({
        targetFile: '.env.example',
        title: 'Add sanitized .env.example template',
        description: 'Provide placeholder configuration template tailored to application dependencies.',
        diff: [
          '--- /dev/null',
          '+++ b/.env.example',
          `@@ -0,0 +1,${templateLines.length} @@`,
          diffBody,
          '',
        ].join('\n'),
      });
    }
  }

  return patches;
}

export default {
  createLineReplacementPatch,
  generateFixPatches,
};
