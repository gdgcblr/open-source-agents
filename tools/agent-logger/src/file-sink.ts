import { constants } from 'node:fs';
import { lstat, mkdir, open, realpath, type FileHandle } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { join, resolve } from 'node:path';
import type { LogEvent, LogSink } from './types.js';

/** Internal append-only sink. The SDK delivery queue serializes writes. */
export class FileSink implements LogSink {
  private bytesWritten = 0;

  private constructor(
    private readonly handle: FileHandle,
    readonly filePath: string,
    private readonly maxBytes: number,
  ) {}

  /** Args: directory and byte limit. Returns: new sink. Raises: on unsafe path or filesystem error. */
  static async open(directory: string, maxBytes: number): Promise<FileSink> {
    if (typeof directory !== 'string' || !directory.trim() || directory.includes('\0')) {
      throw new TypeError('directory must be a non-empty filesystem path.');
    }
    const path = resolve(directory);
    await mkdir(path, { recursive: true, mode: 0o700 });
    const metadata = await lstat(path);
    if (
      !metadata.isDirectory() ||
      metadata.isSymbolicLink() ||
      (metadata.mode & 0o077) !== 0
    ) {
      throw new Error('Log directory must be private (0700) and must not be a symlink.');
    }
    const canonical = await realpath(path);
    const filePath = join(canonical, `run-${randomUUID()}.jsonl`);
    const flags =
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW;
    const handle = await open(filePath, flags, 0o600);
    return new FileSink(handle, filePath, maxBytes);
  }

  /** Args: sanitized event. Returns: completion. Raises: on quota or I/O error. */
  async write(event: LogEvent): Promise<void> {
    const line = `${JSON.stringify(event)}\n`;
    const bytes = Buffer.byteLength(line);
    if (this.bytesWritten + bytes > this.maxBytes)
      throw new Error('Log file byte limit reached.');
    this.bytesWritten += bytes;
    await this.handle.writeFile(line);
  }

  /** Args: none. Returns: sync and close completion. Raises: on filesystem error. */
  async close(): Promise<void> {
    try {
      await this.handle.sync();
    } finally {
      await this.handle.close();
    }
  }
}
