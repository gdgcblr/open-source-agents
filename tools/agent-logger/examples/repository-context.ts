import { constants } from 'node:fs';
import { open, realpath } from 'node:fs/promises';
import { join, sep } from 'node:path';

/** Args: repository root. Returns: bounded public README/package context. Raises: invalid root, unsafe path or I/O error. */
export async function readRepositoryContext(directory: string): Promise<string> {
  const root = await realpath(directory);
  const sections = await Promise.all(
    ['README.md', 'package.json'].map(async (name) => {
      const target = await realpath(join(root, name));
      if (!target.startsWith(root + sep))
        throw new Error('Context file escapes the selected repository.');
      const handle = await open(
        target,
        constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
      );
      try {
        const metadata = await handle.stat();
        if (!metadata.isFile())
          throw new Error('Expected a regular public context file.');
        const buffer = Buffer.alloc(Math.min(metadata.size, 2048));
        const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
        return `${name}:\n${buffer.subarray(0, bytesRead).toString('utf8')}`;
      } finally {
        await handle.close();
      }
    }),
  );
  return sections.join('\n\n');
}
