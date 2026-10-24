/**
 * PR Sentinel - Open-Source Compliance & Guidelines Validator
 * Verifies repository standards defined in CONTRIBUTING.md.
 */

import fs from 'node:fs';
import path from 'node:path';

export const REQUIRED_README_SECTIONS = [
  'Overview',
  'Technical Stack',
  'Architecture',
  'Prerequisites',
  'Installation',
  'Configuration',
  'How to Run',
  'Example',
  'How to Test',
  'Known Limitations',
  'Security',
  'License',
];

/**
 * Audit project directory against open-source contribution guidelines
 * @param {string} projectDir Absolute or relative path to project folder
 * @param {Array<string>} [changedFilesList] List of all changed files in PR
 * @returns {Object} Compliance audit report
 */
export function auditProjectCompliance(projectDir, changedFilesList = []) {
  const resolvedDir = path.resolve(process.cwd(), projectDir);
  const folderName = path.basename(resolvedDir);
  const parentFolder = path.basename(path.dirname(resolvedDir));

  const violations = [];
  const warnings = [];

  // 1. Directory & Naming Convention
  const isKebabCase = /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(folderName);
  if (!isKebabCase) {
    violations.push({
      rule: 'NAMING_CONVENTION',
      severity: 'HIGH',
      message: `Directory name "${folderName}" must be lowercase kebab-case (e.g., "my-agent").`,
    });
  }

  const genericNames = ['my-agent', 'test', 'demo', 'final-project', 'my-tool', 'helper'];
  if (genericNames.includes(folderName)) {
    violations.push({
      rule: 'DESCRIPTIVE_NAMING',
      severity: 'HIGH',
      message: `Directory name "${folderName}" is too generic. Choose a descriptive name reflecting its function.`,
    });
  }

  // 2. Location category
  const validParents = ['agents', 'tools'];
  const isValidCategory = validParents.includes(parentFolder);
  if (!isValidCategory && !resolvedDir.includes('agents') && !resolvedDir.includes('tools')) {
    warnings.push({
      rule: 'CATEGORY_LOCATION',
      message: `Project resides in "${parentFolder}/", but contributions must be under "agents/<slug>/" or "tools/<slug>/".`,
    });
  }

  // 3. README Presence and Completeness
  const readmePath = path.join(resolvedDir, 'README.md');
  const hasReadme = fs.existsSync(readmePath);
  let readmeCompleteness = 0;
  const missingSections = [];

  if (!hasReadme) {
    violations.push({
      rule: 'README_MISSING',
      severity: 'CRITICAL',
      message: 'Missing README.md in project directory.',
    });
  } else {
    try {
      const readmeContent = fs.readFileSync(readmePath, 'utf8');

      // Check for unfilled placeholder tokens from template
      const placeholderRegex = /\[Project Name\]|\[One-sentence summary\]|\[Language Runtime\]|<project-slug>/g;
      const placeholdersFound = readmeContent.match(placeholderRegex);
      if (placeholdersFound && placeholdersFound.length > 2) {
        warnings.push({
          rule: 'TEMPLATE_PLACEHOLDERS',
          message: `README.md contains ${placeholdersFound.length} unmodified template placeholder(s) like "${placeholdersFound[0]}".`,
        });
      }

      // Check required sections
      for (const section of REQUIRED_README_SECTIONS) {
        const regex = new RegExp(`##.*${section}`, 'i');
        if (!regex.test(readmeContent)) {
          missingSections.push(section);
        }
      }

      readmeCompleteness = Math.round(
        ((REQUIRED_README_SECTIONS.length - missingSections.length) / REQUIRED_README_SECTIONS.length) * 100
      );

      if (missingSections.length > 0) {
        warnings.push({
          rule: 'README_INCOMPLETE_SECTIONS',
          message: `README.md is missing ${missingSections.length} recommended section(s): ${missingSections.slice(0, 4).join(', ')}${missingSections.length > 4 ? '...' : ''}.`,
        });
      }
    } catch (e) {
      violations.push({
        rule: 'README_READ_ERROR',
        severity: 'MEDIUM',
        message: `Could not read README.md: ${e.message}`,
      });
    }
  }

  // 4. .env.example Presence
  const envExamplePath = path.join(resolvedDir, '.env.example');
  const hasEnvExample = fs.existsSync(envExamplePath);
  if (!hasEnvExample) {
    warnings.push({
      rule: 'ENV_EXAMPLE_MISSING',
      message: 'Missing .env.example file with placeholder environment variables.',
    });
  }

  // 5. .gitignore Presence
  const gitignorePath = path.join(resolvedDir, '.gitignore');
  const hasGitignore = fs.existsSync(gitignorePath);
  if (!hasGitignore) {
    warnings.push({
      rule: 'GITIGNORE_MISSING',
      message: 'Missing local .gitignore file to prevent accidental secret or dependency commits.',
    });
  }

  // 6. Manifest Presence
  const manifests = ['package.json', 'requirements.txt', 'pyproject.toml', 'Cargo.toml', 'go.mod'];
  const foundManifest = manifests.find(m => fs.existsSync(path.join(resolvedDir, m)));
  const hasManifest = Boolean(foundManifest);
  if (!hasManifest) {
    violations.push({
      rule: 'MANIFEST_MISSING',
      severity: 'HIGH',
      message: 'No dependency manifest found (package.json, requirements.txt, pyproject.toml, etc.).',
    });
  }

  // 7. Isolation Check across PR changed files
  let isIsolated = true;
  if (changedFilesList && changedFilesList.length > 0) {
    const slug = path.basename(resolvedDir);
    const outsideFiles = changedFilesList.filter(file => {
      const normalized = file.replace(/\\/g, '/');
      // Allowed modifications outside: agents/README.md or tools/README.md index tables
      if (normalized === 'agents/README.md' || normalized === 'tools/README.md') return false;
      return !normalized.includes(`/${slug}/`) &&
             !normalized.startsWith(`${slug}/`) &&
             !normalized.startsWith(`agents/${slug}/`) &&
             !normalized.startsWith(`tools/${slug}/`);
    });

    if (outsideFiles.length > 0) {
      isIsolated = false;
      violations.push({
        rule: 'CROSS_PROJECT_POLLUTION',
        severity: 'HIGH',
        message: `PR modifies ${outsideFiles.length} file(s) outside project directory (${outsideFiles.slice(0, 3).join(', ')}).`,
      });
    }
  }

  const score = Math.max(0, 100 - (violations.length * 25) - (warnings.length * 5));

  return {
    folderName,
    hasReadme,
    readmeCompleteness,
    missingSections,
    hasEnvExample,
    hasGitignore,
    hasManifest,
    manifestType: foundManifest || 'none',
    isIsolated,
    score,
    isCompliant: violations.length === 0,
    violations,
    warnings,
  };
}

export default {
  REQUIRED_README_SECTIONS,
  auditProjectCompliance,
};
