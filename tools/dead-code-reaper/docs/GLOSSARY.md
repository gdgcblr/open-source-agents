# Glossary

The project's own words, agreed once. Vocabulary only: no implementation details.

**Dead code**
Code in a Python project that can be deleted without changing what the project does.
Five kinds are in scope: unused definitions, unused imports, unused variables, unused
modules, and unreachable code. Test-only code is not dead code.

**Definition**
A function, class, or method defined with `def`, `async def`, or `class`.

**Unused definition**
A definition that nothing in the project uses.

**Unused variable**
A variable inside a function that is given a value and never read.

**Unused import**
An imported name that nothing in the importing module uses.

**Unused module**
A `.py` file that nothing imports and that is not run directly.

**Unreachable code**
Statements that can never execute, wherever they appear in a module or function.

**Scan**
The command that finds dead code by reading the project. It never runs project code
and never changes files.

**Run**
The command that finds dead code, proves each removal against the project's tests,
and produces a patch the user can apply.

**Apply**
The command that carries out a developer's human review choices. It runs the project's
tests once on exactly the chosen removals, and only if they pass does it change the
files and save the changes as a patch.

**Report**
A single self-contained HTML file, opened in any browser, that shows dead code
highlighted in a folder and file view. It is where human review happens.

**Application mode**
How the tool treats a project that nothing outside the repo imports: if nothing in the
repo uses a definition, it is dead.

**Library mode**
How the tool treats a project that other projects install and import: public names
(those not starting with `_`) are assumed to be used elsewhere and are never dead.

**Verified**
A removal the project's tests still pass without.

**Unverified**
A removal that could only be checked by compiling and importing the project, because
the project has no tests. Unverified removals start out kept during human review.

**Removal**
One piece of dead code that `run` proposes to delete.

**Unverified removal**
A removal that could not be proven against tests, because the project has no tests or
the limit on test runs was reached. It has only passed a check that every module still
compiles and imports. It starts out kept during human review.

**Human review**
The step in `run` where a developer looks at the proposed removals and marks any they
want to keep before the patch is written. Choices apply to that run only.

**Keep**
A human review decision to leave a removal out of the patch.

**AI note**
A one-line summary, written by an AI model, of what a removal's code did. Shown during
human review so the developer can decide without opening the file.

**Risk warning**
An AI model's flag that a removal may still be used in a way neither reading the code
nor running the tests can show, such as a framework hook or a plugin entry point.
Removals with a risk warning start out kept during human review.

**Test-only code**
A definition used by test files and by nothing else. It is reported in its own list
and is never treated as dead code.
