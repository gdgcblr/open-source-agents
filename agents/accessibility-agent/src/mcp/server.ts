import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { auditPage } from '../core/audit.js';
import { formatAxeResultsAsJson } from '../core/reporter.js';
import { suggestA11yFix } from '../agent/ai-fixer.js';

// Initialize the MCP server instance
const server = new McpServer({
  name: 'accessibility-agent',
  version: '1.0.0',
});

// Tool 1: Audit a page URL using Axe-core
server.tool(
  'audit',
  'Audits a given URL for accessibility issues using Axe-core.',
  {
    url: z.string().url().describe('The web page URL to audit'),
  },
  async ({ url }) => {
    try {
      const auditResults = await auditPage(url);
      const report = formatAxeResultsAsJson(auditResults);
      return {
        content: [
          {
            type: 'text',
            text: typeof report === 'string' ? report : JSON.stringify(report, null, 2),
          },
        ],
      };
    } catch (error) {
      return {
        isError: true,
        content: [
          {
            type: 'text',
            text: `Audit failed: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
      };
    }
  }
);

// Tool 2: Suggest and apply fixes for an a11y issue
server.tool(
  'fix_a11y_issue',
  'Suggests and applies fixes for a given accessibility issue.',
  {
    filePath: z.string().describe('Path to the target component file'),
    lineNumber: z.number().int().positive().describe('Line number where the violation occurs'),
    issueDescription: z.string().describe('Detailed description or rule ID of the accessibility violation'),
  },
  async ({ filePath, lineNumber, issueDescription }) => {
    try {
      // Placeholder or read the actual source snippet
      const dummyCodeSnippet = '<div class="my-element"></div>';
      const suggestion = await suggestA11yFix(dummyCodeSnippet, issueDescription);
      const applied = true; // Replace with applyA11yFix(filePath, lineNumber, dummyCodeSnippet, suggestion) when ready

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(
              {
                filePath,
                lineNumber,
                suggestion,
                applied,
              },
              null,
              2
            ),
          },
        ],
      };
    } catch (error) {
      return {
        isError: true,
        content: [
          {
            type: 'text',
            text: `Fix suggestion failed: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
      };
    }
  }
);

// Start the stdio transport
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('MCP Server for Accessibility Agent started on stdio.');
}

main().catch((err) => {
  console.error('Fatal error starting MCP Server:', err);
  process.exit(1);
});