# Running FirstRun on pull requests

`firstrun-pr-check.yml` is an example GitHub Actions workflow for a monorepo like
`gdgcblr/open-source-agents`. On every pull request that touches `agents/**` or `tools/**` it:

1. works out which project folders (`agents/<slug>`, `tools/<slug>`) the PR changed,
2. runs `python -m firstrun <folder> --sandbox docker --ci --comment-file ...` on each one,
3. appends every `report.md` to the job summary and uploads `runs/` as the `firstrun-runs` artifact,
4. posts one PR comment (or updates the previous one, found by the `<!-- firstrun-report -->` marker).

The job fails when a project does not run as documented (`--ci` exit 1) or FirstRun could not run
(exit 3). A project that needs credentials (exit 2) only raises a warning, because PRs from forks
never get secrets and most AI projects need a key.

It lives in this folder because contributions here may not touch the repo root. To adopt it, copy it
to `.github/workflows/firstrun-pr-check.yml`.

## Gemini key

Add a repository secret `GEMINI_API_KEY` to let FirstRun use Gemini for planning and investigation.
Without it (and on every fork PR, where secrets are empty) FirstRun uses its offline rules. The key is
FirstRun's own: it is never passed into the project under test, so a submission cannot read it.

## Comments on PRs from forks

A `pull_request` run from a fork gets a read-only `GITHUB_TOKEN`, so the "Post or update the PR
comment" step only runs for branches in the same repository. For fork PRs, use a second workflow that
runs after the check in the base repository's context and only posts the text artifact:

```yaml
# .github/workflows/firstrun-comment.yml
name: FirstRun comment

on:
  workflow_run:
    workflows: ["FirstRun README check"]
    types: [completed]

permissions:
  actions: read
  pull-requests: write

jobs:
  comment:
    if: >-
      github.event.workflow_run.event == 'pull_request' &&
      github.event.workflow_run.head_repository.full_name != github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        continue-on-error: true
        with:
          name: firstrun-comment
          run-id: ${{ github.event.workflow_run.id }}
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (!fs.existsSync('firstrun-comment.md') || !fs.existsSync('pr-number.txt')) return;
            const issue_number = Number(fs.readFileSync('pr-number.txt', 'utf8').trim());
            if (!Number.isInteger(issue_number) || issue_number <= 0) return;
            const { owner, repo } = context.repo;
            // the artifact was produced by PR code, so make sure it belongs to this run's commit
            const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: issue_number });
            if (pr.head.sha !== context.payload.workflow_run.head_sha) {
              core.warning('PR head moved since the check ran, skipping the comment');
              return;
            }
            const marker = '<!-- firstrun-report -->';
            let body = fs.readFileSync('firstrun-comment.md', 'utf8').slice(0, 65000);
            if (!body.startsWith(marker)) body = marker + '\n' + body;
            const comments = await github.paginate(github.rest.issues.listComments, {
              owner, repo, issue_number, per_page: 100,
            });
            const mine = comments.find(c => c.user.type === 'Bot' && (c.body || '').startsWith(marker));
            if (mine) {
              await github.rest.issues.updateComment({ owner, repo, comment_id: mine.id, body });
            } else {
              await github.rest.issues.createComment({ owner, repo, issue_number, body });
            }
```

This is the pattern GitHub recommends over `pull_request_target`: the job with the write token never
checks out or runs PR code, it only reads a text file. Avoid `pull_request_target` here. It would run
with a write token and secrets, and FirstRun's whole job is executing the PR's README commands.

## Security trade-off

FirstRun executes the commands written in the PR's README. In CI that is the same trust level as any
test job that runs PR code. The commands run inside a throwaway Docker container on a disposable
runner, with the read-only token and no secrets, and FirstRun copies the project in rather than mounting
it. The comment text is produced by PR-controlled code, so treat it like any other contributor comment.
It is posted as plain markdown and nothing in it is executed. Maintainers who want to vet first can
require approval for workflows from first-time contributors in the repository's Actions settings.
