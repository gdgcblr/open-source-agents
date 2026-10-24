import * as core from '@actions/core';
import * as github from '@actions/github';
import { auditPage } from '../core/audit';
import { formatAxeResultsAsGitHubPRMarkdown, formatSuggestedFixesReport } from '../core/reporter';
import { suggestA11yFix, suggestAllA11yFixes, applyA11yFix } from '../agent/ai-fixer';
import { AxeResults, Result } from 'axe-core';

interface PullRequestContext {
  owner: string;
  repo: string;
  pull_number: number;
  base_ref: string;
  head_ref: string;
}

async function getPullRequestContext(): Promise<PullRequestContext | null> {
  const pullRequest = github.context.payload.pull_request;
  if (!pullRequest) {
    core.error('This action can only be run on pull_request events.');
    return null;
  }

  return {
    owner: github.context.repo.owner,
    repo: github.context.repo.repo,
    pull_number: pullRequest.number,
    base_ref: pullRequest.base.ref,
    head_ref: pullRequest.head.ref,
  };
}

async function postComment(context: PullRequestContext, commentBody: string) {
  const token = process.env.GITHUB_TOKEN || core.getInput('github-token', { required: true });
  const octokit = github.getOctokit(token);

  await octokit.rest.issues.createComment({
    owner: context.owner,
    repo: context.repo,
    issue_number: context.pull_number,
    body: commentBody,
  });
}

async function createFixPullRequest(
  context: PullRequestContext,
  octokit: ReturnType<typeof github.getOctokit>,
  suggestedFixes: { description: string; suggestedFix: string; htmlSnippet: string; }[]
) {
  const newBranchName = `a11y-fix-${Date.now()}`;
  const baseBranchSha = github.context.sha; // SHA of the commit that triggered the workflow

  // 1. Create a new branch
  await octokit.rest.git.createRef({
    owner: context.owner,
    repo: context.repo,
    ref: `refs/heads/${newBranchName}`,
    sha: baseBranchSha,
  });
  core.info(`Created new branch: ${newBranchName}`);

  // 2. Prepare file content (simulated fix file)
  const fixReportContent = formatSuggestedFixesReport(suggestedFixes, 'markdown');
  const fixFileName = `a11y-suggested-fixes-${Date.now()}.md`;
  const fixFilePath = `agents/accessibility-agent/${fixFileName}`;

  // 3. Get the current tree to base new commit off
  const { data: { tree } } = await octokit.rest.git.getCommit({
    owner: context.owner,
    repo: context.repo,
    commit_sha: baseBranchSha,
  });

  // 4. Create a new tree with the fix file
  const { data: newTree } = await octokit.rest.git.createTree({
    owner: context.owner,
    repo: context.repo,
    base_tree: tree.sha,
    tree: [
      {
        path: fixFilePath,
        mode: '100644', // file mode
        type: 'blob',
        content: fixReportContent,
      },
    ],
  });

  // 5. Create a new commit
  const { data: newCommit } = await octokit.rest.git.createCommit({
    owner: context.owner,
    repo: context.repo,
    message: `feat(a11y): apply suggested fixes for accessibility issues`,
    tree: newTree.sha,
    parents: [baseBranchSha],
  });
  core.info(`Created new commit: ${newCommit.sha}`);

  // 6. Update the new branch to point to the new commit
  await octokit.rest.git.updateRef({
    owner: context.owner,
    repo: context.repo,
    ref: `refs/heads/${newBranchName}`,
    sha: newCommit.sha,
  });
  core.info(`Updated branch ${newBranchName} with commit ${newCommit.sha}`);

  // 7. Create the pull request
  const { data: pullRequest } = await octokit.rest.pulls.create({
    owner: context.owner,
    repo: context.repo,
    title: `feat(a11y): Suggested accessibility fixes for PR #${context.pull_number}`,
    head: newBranchName,
    base: context.base_ref, // Target the base branch of the original PR
    body: `This PR proposes automated accessibility fixes based on the audit performed on PR #${context.pull_number}.
Please review the changes in \`${fixFileName}\` and apply them to your codebase.`,
  });

  core.info(`Created new pull request: ${pullRequest.html_url}`);
  await postComment(
    context,
    `🔔 An automated PR with suggested accessibility fixes has been created: ${pullRequest.html_url}`
  );
}

async function runAudit(context: PullRequestContext, targetUrl: string) {
  core.info(`Running accessibility audit on ${targetUrl}`);
  const auditResults = await auditPage(targetUrl);
  const markdownReport = formatAxeResultsAsGitHubPRMarkdown(auditResults);

  await postComment(context, markdownReport);

  if (auditResults.violations && auditResults.violations.length > 0) {
    core.info('Accessibility violations found. Generating suggested fixes...');
    const suggestedFixes = await suggestAllA11yFixes(auditResults);

    if (suggestedFixes.length > 0) {
      core.info('Creating a new PR with suggested fixes.');
      const token = process.env.GITHUB_TOKEN || core.getInput('github-token', { required: true });
      const octokit = github.getOctokit(token);
      await createFixPullRequest(context, octokit, suggestedFixes);
    } else {
      core.info('No suggested fixes generated for the identified violations.');
    }
  } else {
    core.info('No accessibility violations found.');
  }
}

async function handleFixCommand(context: PullRequestContext, commentBody: string) {
  const fixCommandRegex = /^\/fix-a11y\s+(\S+)\s+(\d+)\s+(.*)/;
  const match = commentBody.match(fixCommandRegex);

  if (match) {
    const [, filePath, lineNumberStr, issueDescription] = match;
    const lineNumber = parseInt(lineNumberStr, 10);

    core.info(`Attempting to fix issue in ${filePath} at line ${lineNumber}: ${issueDescription}`);

    // In a real scenario, you'd read the file content to get the snippet
    const dummyCodeSnippet = '<img src=\"old.png\" alt=\"\"><br/>'; // Placeholder

    const suggestion = await suggestA11yFix(dummyCodeSnippet, issueDescription);
    const applied = await applyA11yFix(filePath, lineNumber, dummyCodeSnippet, suggestion);

    if (applied) {
      await postComment(context, `✅ Applied fix to ${filePath} line ${lineNumber}. Suggested change: \n\`\`\`html\n${suggestion}\n\`\`\``);
    } else {
      await postComment(context, `❌ Failed to apply fix to ${filePath} line ${lineNumber}. Suggested change: \n\`\`\`html\n${suggestion}\n\`\`\``);
    }

  } else {
    await postComment(context, 'Invalid /fix-a11y command. Usage: `/fix-a11y <filePath> <lineNumber> <issueDescription>`');
  }
}

async function main() {
  try {
    const context = await getPullRequestContext();
    if (!context) return;

    const eventName = github.context.eventName;
    const payload = github.context.payload;

    if (eventName === 'pull_request') {
      const pr = payload.pull_request;
      if (!pr || !pr.head.ref) {
        core.error('Could not get pull request head ref.');
        return;
      }
      const previewUrl = process.env.TARGET_URL || core.getInput('preview-url', { required: false });
      if (previewUrl) {
        await runAudit(context, previewUrl);
      } else {
        core.warning('No preview-url provided. Skipping automatic audit.');
        await postComment(context, 'Accessibility audit skipped: No `preview-url` provided. To run a manual audit, comment `/audit-a11y <url>` or push changes to `demo/index.html`.');
      }
    } else if (eventName === 'push' && github.context.ref === `refs/heads/${github.context.payload.repository?.default_branch}`) { // Changed github.ref to github.context.ref
      // Trigger audit on push to default branch only if relevant files are changed
      const filesChanged = github.context.payload.commits?.flatMap((commit: any) => [...commit.added, ...commit.modified]) || []; // Added type any for commit
      const relevantFilesChanged = filesChanged.some((file: any) => // Added type any for file
        file.startsWith('agents/accessibility-agent/') ||
        file.startsWith('.github/workflows/a11y-agent.yml') ||
        file === 'demo/index.html'
      );

      if (relevantFilesChanged) {
        core.info('Relevant files changed on push to default branch. Running audit.');
        const previewUrl = process.env.TARGET_URL || core.getInput('preview-url', { required: false });
        if (previewUrl) {
          await runAudit(context, previewUrl);
        } else {
          core.warning('No preview-url provided for push event. Skipping audit.');
        }
      } else {
        core.info('No relevant files changed on push to default branch. Skipping audit.');
      }
    } else if (eventName === 'issue_comment' && payload.action === 'created') {
      const commentBody = payload.comment?.body;
      if (commentBody) {
        if (commentBody.startsWith('/audit-a11y')) {
          const url = commentBody.split(' ')[1];
          if (url) {
            await runAudit(context, url);
          } else {
            await postComment(context, 'Invalid /audit-a11y command. Usage: `/audit-a11y <url>`');
          }
        } else if (commentBody.startsWith('/fix-a11y')) {
          await handleFixCommand(context, commentBody);
        }
      }
    }
  } catch (error: any) {
    core.setFailed(error.message);
  }
}

main();