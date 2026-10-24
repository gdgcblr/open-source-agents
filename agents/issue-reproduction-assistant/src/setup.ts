import { readFile, stat } from "node:fs/promises";
import path from "node:path";

export interface ProjectSetup {
  ecosystem: "node" | "unknown";
  packageManager?: "npm" | "pnpm" | "yarn" | "bun";
  nodeVersion?: string;
  framework?: string;
  installCommand?: string;
  runCommand?: string;
  buildCommand?: string;
  defaultUrl?: string;
}

const FRAMEWORKS: Array<{ dependency: string; name: string; port: number }> = [
  { dependency: "astro", name: "Astro", port: 4321 },
  { dependency: "next", name: "Next.js", port: 3000 },
  { dependency: "nuxt", name: "Nuxt", port: 3000 },
  { dependency: "@sveltejs/kit", name: "SvelteKit", port: 5173 },
  { dependency: "@angular/core", name: "Angular", port: 4200 },
  { dependency: "vite", name: "Vite", port: 5173 },
  { dependency: "react-scripts", name: "Create React App", port: 3000 },
  { dependency: "react", name: "React", port: 3000 },
  { dependency: "vue", name: "Vue", port: 5173 },
];

async function exists(file: string): Promise<boolean> {
  try {
    await stat(file);
    return true;
  } catch {
    return false;
  }
}

async function readText(file: string): Promise<string | undefined> {
  try {
    return (await readFile(file, "utf8")).trim();
  } catch {
    return undefined;
  }
}

/** Best-effort, read-only detection of how to install and start a project. */
export async function detectSetup(repositoryPath: string): Promise<ProjectSetup> {
  const raw = await readText(path.join(repositoryPath, "package.json"));
  if (!raw) {
    return { ecosystem: "unknown" };
  }

  let manifest: {
    scripts?: Record<string, string>;
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
    engines?: { node?: string };
  };
  try {
    manifest = JSON.parse(raw);
  } catch {
    return { ecosystem: "node" };
  }

  const packageManager = (await exists(path.join(repositoryPath, "pnpm-lock.yaml")))
    ? "pnpm"
    : (await exists(path.join(repositoryPath, "yarn.lock")))
      ? "yarn"
      : (await exists(path.join(repositoryPath, "bun.lockb"))) || (await exists(path.join(repositoryPath, "bun.lock")))
        ? "bun"
        : "npm";

  const hasLockfile =
    packageManager !== "npm" || (await exists(path.join(repositoryPath, "package-lock.json")));
  const installCommand =
    packageManager === "npm" ? (hasLockfile ? "npm ci" : "npm install") : `${packageManager} install`;

  const scripts = manifest.scripts ?? {};
  const scriptName = ["dev", "start", "serve", "preview"].find((name) => scripts[name]);
  const run = (name: string): string => (packageManager === "npm" ? `npm run ${name}` : `${packageManager} run ${name}`);

  const dependencies = { ...manifest.dependencies, ...manifest.devDependencies };
  const framework = FRAMEWORKS.find((item) => item.dependency in dependencies);
  const nodeVersion =
    (await readText(path.join(repositoryPath, ".nvmrc")))?.replace(/^v/, "") ?? manifest.engines?.node;

  const explicitPort = scriptName ? /(?:--port|-p)[ =](\d{2,5})/.exec(scripts[scriptName])?.[1] : undefined;
  const port = explicitPort ?? (framework ? String(framework.port) : undefined);

  return {
    ecosystem: "node",
    packageManager,
    nodeVersion,
    framework: framework?.name,
    installCommand,
    runCommand: scriptName ? run(scriptName) : undefined,
    buildCommand: scripts.build ? run("build") : undefined,
    defaultUrl: port ? `http://localhost:${port}` : undefined,
  };
}
