import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface CommitInfo {
  hash: string;
  date: string;
  author: string;
  subject: string;
}

/** Read-only `git log` for one file. Returns [] if the path is not in a git repository. */
export async function getFileHistory(
  repositoryPath: string,
  relativeFile: string,
  limit = 5,
): Promise<CommitInfo[]> {
  const root = path.resolve(repositoryPath);
  const absolute = path.resolve(root, relativeFile);
  if (absolute !== root && !absolute.startsWith(root + path.sep)) {
    throw new Error("File path escapes the repository.");
  }

  try {
    const { stdout } = await execFileAsync(
      "git",
      [
        "-c", "core.fsmonitor=false",
        "-C", root,
        "log", `-n${Math.min(Math.max(limit, 1), 20)}`,
        "--format=%h%x1f%ad%x1f%an%x1f%s", "--date=short", "--",
        path.relative(root, absolute),
      ],
      { timeout: 15_000, maxBuffer: 1024 * 1024 },
    );
    return stdout
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [hash, date, author, subject] = line.split("\u001f");
        return { hash, date, author, subject };
      });
  } catch {
    return [];
  }
}
