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
 * @returns {Array<Object>} Generated patches
 */
export function generateFixPatches(issues = []) {
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
      patches.push({
        targetFile: '.env.example',
        title: 'Add sanitized .env.example template',
        description: 'Provide placeholder configuration template for contributors.',
        diff: [
          '--- /dev/null',
          '+++ b/.env.example',
          '@@ -0,0 +1,5 @@',
          '+# API Keys and Model Configuration',
          '+GEMINI_API_KEY=your_gemini_api_key_here',
          '+GEMINI_MODEL=gemini-2.5-flash',
          '+PORT=3737',
          '+LOG_LEVEL=info',
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
