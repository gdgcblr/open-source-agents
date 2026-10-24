# FirstRun Doctor

**Check whether a Python project's example actually works.**

You download a project, follow its instructions, and run it. Something fails, or
it prints "Success" without creating the promised report.

FirstRun Doctor records what happened, points to useful evidence, and checks the
result again after you make a fix.

## Who it helps

Students trying a project, developers sharing examples, maintainers reviewing
contributions, and teachers running workshops.

## Problems it solves

- **Unclear errors:** highlights relevant error messages and a suggested next step.
- **Missing settings:** names required settings that have not been configured.
- **False success:** checks whether the promised output was actually created.
- **Old results:** prevents yesterday's report from making today's check pass.
- **Uncertain fixes:** compares the same checks before and after a change.

## How it works

1. Choose a local Python project.
2. List the command and expected result in a small `doctor.json` file.
3. Review the command and allow it to run.
4. See what passed, failed, or could not be verified.
5. Fix the project, run it again, and share the comparison.

## Six useful examples

| Situation | What Doctor does |
| --- | --- |
| A student forgets a required API key. | Names the missing setting without showing its private value. |
| An agent prints "Report created" but writes nothing. | Reports that the expected file is missing. |
| A maintainer finds an old report in a contribution. | Checks a fresh run without reusing that file. |
| A data tool saves an empty list. | Fails the check if the contract requires a nonempty list. |
| A program reports a missing Python package. | Highlights the error so the developer can fix the environment and rerun. |
| A workshop example gets stuck. | Stops it at the chosen time limit and reports completion as unverified. |

## What the result means

- **Verified:** the example ran and met its declared output checks.
- **Failed:** an observed error or output broke a check.
- **Unknown:** execution or evidence was incomplete.

Jev is optional. It can suggest a likely cause from the evidence. The actual
checks decide whether the example passed; a model suggestion never proves it.

The first version supports local Python scripts and JSON reports. People apply
fixes themselves. Passing one example does not prove the whole project is
bug-free or every answer is correct.

See the [README](README.md) to install and run it, or the [plan](PLAN.md) for scope.
