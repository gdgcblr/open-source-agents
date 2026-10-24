import { GoogleGenerativeAI } from "@google/generative-ai";
import * as dotenv from 'dotenv';
import { AxeResults, Result } from 'axe-core'; // Import AxeResults and Result
dotenv.config();

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';

if (!GEMINI_API_KEY) {
  throw new Error("GEMINI_API_KEY is not set in the environment variables.");
}

const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);

export async function suggestA11yFix(codeSnippet: string, issueDescription: string): Promise<string> {
  const model = genAI.getGenerativeModel({ model: "gemini-3.1-pro-preview" }); // Updated model

  const prompt = `You are an expert Accessibility (a11y) Specialist. You are provided with a code snippet and an accessibility issue description. Your task is to provide a corrected code snippet that addresses the accessibility issue. ONLY return the corrected code snippet, do not include any additional text or explanations.

Code Snippet:
\`\`\`
${codeSnippet}
\`\`\`

Accessibility Issue:
${issueDescription}

Corrected Code Snippet:`;

  const result = await model.generateContent(prompt);
  const response = await result.response;
  const text = response.text();

  return text;
}

export async function suggestAllA11yFixes(auditResults: AxeResults): Promise<{ description: string; suggestedFix: string; htmlSnippet: string; }[]> {
  const allSuggestedFixes: { description: string; suggestedFix: string; htmlSnippet: string; }[] = [];

  for (const violation of auditResults.violations) {
    for (const node of violation.nodes) {
      const issueDescription = `${violation.help} (Impact: ${violation.impact || 'N/A'}). Element: ${node.html}`;
      const suggestedFix = await suggestA11yFix(node.html, issueDescription);
      allSuggestedFixes.push({
        description: issueDescription,
        suggestedFix: suggestedFix,
        htmlSnippet: node.html,
      });
    }
  }

  return allSuggestedFixes;
}

export async function applyA11yFix(filePath: string, lineNumber: number, originalCode: string, suggestedFix: string): Promise<boolean> {
  // In a real-world scenario, this function would modify the file at filePath
  // For now, we'll just log the action.
  console.log(`Applying fix to ${filePath} at line ${lineNumber}:`);
  console.log(`Original Code:\n${originalCode}`);
  console.log(`Suggested Fix:\n${suggestedFix}`);
  return true;
}