import { Command } from 'commander';
import { auditPage } from './core/audit';
import { formatAxeResultsAsJson, formatAxeResultsAsGitHubPRMarkdown, formatAxeResultsAsPdf } from './core/reporter';
import { suggestA11yFix, applyA11yFix } from './agent/ai-fixer';
import { mapDomToSource } from './agent/mapper';

const program = new Command();

program
  .name('accessibility-agent')
  .description('CLI for the Accessibility CI/CD Audit & Remediation Agent')
  .version('1.0.0');

program.command('audit <url>')
  .description('Audits a given URL for accessibility issues')
  .option('-f, --format <type>', 'Output format: json, markdown, or pdf', 'json')
  .option('-o, --output <path>', 'Output file path for PDF reports')
  .action(async (url, options) => {
    console.log(`Auditing ${url}...`);
    const results = await auditPage(url);
    if (options.format === 'markdown') {
      console.log(formatAxeResultsAsGitHubPRMarkdown(results));
    } else if (options.format === 'pdf') {
      if (!options.output) {
        console.error('Error: --output option is required for PDF format.');
        process.exit(1);
      }
      await formatAxeResultsAsPdf(results, options.output);
      console.log(`PDF report saved to ${options.output}`);
    } else {
      console.log(formatAxeResultsAsJson(results));
    }
  });

program.command('fix <filePath> <lineNumber> <issueDescription>')
  .description('Suggests and applies a fix for an accessibility issue')
  .action(async (filePath, lineNumber, issueDescription) => {
    console.log(`Attempting to fix issue in ${filePath} at line ${lineNumber}...`);

    // In a real scenario, you'd read the code snippet from the file
    const dummyCodeSnippet = '<div class=\"my-element\"></div>'; // Placeholder

    const suggestion = await suggestA11yFix(dummyCodeSnippet, issueDescription);
    console.log('Suggested Fix:', suggestion);

    const applied = await applyA11yFix(filePath, parseInt(lineNumber, 10), dummyCodeSnippet, suggestion);
    if (applied) {
      console.log('Fix applied successfully.');
    } else {
      console.log('Failed to apply fix.');
    }
  });

program.command('map <domSelectorOrHtmlSnippet>')
  .description('Maps a DOM selector or HTML snippet to source files')
  .action(async (domSelectorOrHtmlSnippet) => {
    console.log(`Mapping ${domSelectorOrHtmlSnippet} to source files...`);
    const mappings = await mapDomToSource(domSelectorOrHtmlSnippet);
    if (mappings.length > 0) {
      console.log('Found mappings:', mappings);
    } else {
      console.log('No mappings found.');
    }
  });

program.parse(process.argv);
