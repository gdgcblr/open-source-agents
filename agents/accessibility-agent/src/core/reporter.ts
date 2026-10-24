import { AxeResults, Result } from 'axe-core';
import { chromium } from 'playwright';

export function formatAxeResultsAsJson(results: AxeResults): string {
  return JSON.stringify(results, null, 2);
}

function generateHtmlReport(results: AxeResults): string {
  let html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Accessibility Audit Report</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 20px; }
        h1, h2, h3 { color: #0056b3; }
        h1 { border-bottom: 2px solid #0056b3; padding-bottom: 10px; }
        h2 { border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }
        code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 4px; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
        .violation { border: 1px solid #e00; padding: 15px; margin-bottom: 15px; border-radius: 5px; background-color: #ffe0e0; }
        .violation h3 { color: #e00; margin-top: 0; }
        .pass { color: #0a0; }
        .incomplete { color: #ffa500; }
        .inapplicable { color: #888; }
    </style>
</head>
<body>
    <h1>Accessibility Audit Report</h1>

`;

  if (results.violations.length > 0) {
    html += `    <h2>Violations</h2>
`;
    results.violations.forEach((violation: Result) => {
      html += `    <div class="violation">
        <h3>[${violation.id}] ${violation.help}</h3>
        <p><strong>Impact</strong>: ${violation.impact || 'N/A'}</p>
        <p><strong>Description</strong>: ${violation.description}</p>
        <p><strong>Help URL</strong>: <a href="${violation.helpUrl}">${violation.helpUrl}</a></p>
        <p><strong>Nodes</strong>:</p>
        <ul>
`;
      violation.nodes.forEach(node => {
        html += `            <li>
                <p><strong>HTML</strong>:</p><pre><code>${escapeHtml(node.html)}</code></pre>
                <p><strong>Target</strong>: <code>${escapeHtml(node.target.join(', '))}</code></p>
`;
        if (node.failureSummary) {
          html += `                <p><strong>Failure Summary</strong>: ${escapeHtml(node.failureSummary)}</p>
`;
        }
        html += `            </li>
`;
      });
      html += `        </ul>
    </div>
`;
    });
  } else {
    html += `    <h2>No Accessibility Violations Found! 🎉</h2>
`;
  }

  if (results.passes.length > 0) {
    html += `    <h2>Passes</h2>
    <ul>
`;
    results.passes.forEach((pass: Result) => {
      html += `        <li class="pass">[${pass.id}] ${pass.help}</li>
`;
    });
    html += `    </ul>
`;
  }

  if (results.incomplete.length > 0) {
    html += `    <h2>Incomplete</h2>
    <ul>
`;
    results.incomplete.forEach((incomplete: Result) => {
      html += `        <li class="incomplete">[${incomplete.id}] ${incomplete.help}</li>
`;
    });
    html += `    </ul>
`;
  }

  if (results.inapplicable.length > 0) {
    html += `    <h2>Inapplicable</h2>
    <ul>
`;
    results.inapplicable.forEach((inapplicable: Result) => {
      html += `        <li class="inapplicable">[${inapplicable.id}] ${inapplicable.help}</li>
`;
    });
    html += `    </ul>
`;
  }

  html += `</body>
</html>`;
  return html;
}

function escapeHtml(unsafe: string): string {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export async function formatAxeResultsAsPdf(results: AxeResults, filePath: string): Promise<void> {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const htmlContent = generateHtmlReport(results);

  await page.setContent(htmlContent, { waitUntil: 'networkidle' });

  await page.pdf({ path: filePath, format: 'A4' });

  await browser.close();
}

export function formatAxeResultsAsGitHubPRMarkdown(results: AxeResults): string {
  let markdown = `# Accessibility Audit Report\n\n`;

  if (results.violations.length > 0) {
    markdown += `## Violations\n\n`;
    results.violations.forEach((violation: Result) => {
      markdown += `### [${violation.id}] ${violation.help}\n`;
      markdown += `**Impact**: ${violation.impact || 'N/A'}\n`;
      markdown += `**Description**: ${violation.description}\n`;
      markdown += `**Help URL**: ${violation.helpUrl}\n`;
      markdown += `**Nodes**:\n`;
      violation.nodes.forEach(node => {
        markdown += `-   **HTML**: \`\`\`html\n${node.html}\n\`\`\`\n`;
        markdown += `    **Target**: \`${node.target.join(', ')}\`\n`;
        if (node.failureSummary) {
          markdown += `    **Failure Summary**: ${node.failureSummary}\n`;
        }
      });
      markdown += `\n`;
    });
  } else {
    markdown += `## No Accessibility Violations Found! 🎉\n\n`;
  }

  if (results.passes.length > 0) {
    markdown += `## Passes\n\n`;
    results.passes.forEach((pass: Result) => {
      markdown += `-   [${pass.id}] ${pass.help}\n`;
    });
    markdown += `\n`;
  }

  if (results.incomplete.length > 0) {
    markdown += `## Incomplete\n\n`;
    results.incomplete.forEach((incomplete: Result) => {
      markdown += `-   [${incomplete.id}] ${incomplete.help}\n`;
    });
    markdown += `\n`;
  }

  if (results.inapplicable.length > 0) {
    markdown += `## Inapplicable\n\n`;
    results.inapplicable.forEach((inapplicable: Result) => {
      markdown += `-   [${inapplicable.id}] ${inapplicable.help}\n`;
    });
    markdown += `\n`;
  }

  return markdown;
}

export function formatSuggestedFixesReport(
  suggestedFixes: { description: string; suggestedFix: string; htmlSnippet: string; }[],
  format: 'markdown' | 'json' = 'markdown'
): string {
  if (format === 'json') {
    return JSON.stringify(suggestedFixes, null, 2);
  }

  let markdown = `## Suggested Accessibility Fixes\n\n`;

  if (suggestedFixes.length === 0) {
    markdown += `No suggested fixes available.\n`;
    return markdown;
  }

  suggestedFixes.forEach((fix, index) => {
    markdown += `### Issue ${index + 1}: ${fix.description}\n`;
    markdown += `**Original HTML Snippet**:\n\`\`\`html\n${fix.htmlSnippet}\n\`\`\`\n`;
    markdown += `**Suggested Fix**:\n\`\`\`html\n${fix.suggestedFix}\n\`\`\`\n\n`;
  });

  return markdown;
}