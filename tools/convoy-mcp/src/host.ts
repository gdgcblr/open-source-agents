import { spawn } from 'node:child_process';

export type HostMessage = Record<string, unknown>;
const DEFAULT_HOST = '/Applications/Convoy.app/Contents/MacOS/NativeMessagingHost';
const MAX_FRAME = 50_000_000;

function stderrTail(stderr: string): string {
  return stderr
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && line !== 'Native messaging host started')
    .join('\n')
    .slice(-4000);
}

export function callHost(message: HostMessage, timeoutMs = 15_000): Promise<HostMessage> {
  const executable = process.env.CONVOY_HOST || DEFAULT_HOST;
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [], { stdio: ['pipe', 'pipe', 'pipe'] });
    const chunks: Buffer[] = [];
    let stderr = '';
    let settled = false;
    let timer: NodeJS.Timeout;
    const finish = (error?: Error, value?: HostMessage) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value!);
    };

    timer = setTimeout(() => {
      child.kill('SIGKILL');
      const diagnostics = stderrTail(stderr);
      finish(new Error(`Convoy host timed out after ${timeoutMs} ms${diagnostics ? `: ${diagnostics}` : ''}`));
    }, timeoutMs);
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (part: string) => { stderr = (stderr + part).slice(-4000); });
    child.stdout.on('data', (part: Buffer) => { chunks.push(part); });
    child.once('error', (error) => finish(new Error(`Could not start Convoy host at ${executable}: ${error.message}`)));
    child.stdin.on('error', (error) => {
      const diagnostics = stderrTail(stderr);
      finish(new Error(`Could not send request to Convoy host: ${error.message}${diagnostics ? `: ${diagnostics}` : ''}`));
    });
    child.once('close', (code, signal) => {
      const output = Buffer.concat(chunks);
      if (output.length < 4) {
        const diagnostics = stderrTail(stderr);
        finish(new Error(`Convoy host returned no response${diagnostics ? `: ${diagnostics}` : ''}${signal ? ` (signal ${signal})` : ` (exit ${code})`}`));
        return;
      }
      const length = output.readUInt32LE(0);
      if (length === 0 || length > MAX_FRAME || output.length < length + 4) {
        finish(new Error('Convoy host returned an invalid or truncated response frame'));
        return;
      }
      try {
        const response = JSON.parse(output.subarray(4, length + 4).toString('utf8')) as HostMessage;
        const diagnostics = stderrTail(stderr);
        if (response.success === false && diagnostics) {
          response.error = `${String(response.error ?? 'Convoy host request failed')} (host stderr: ${diagnostics})`;
        }
        finish(undefined, response);
      } catch (error) {
        finish(new Error(`Convoy host returned invalid JSON: ${String(error)}`));
      }
    });
    const body = Buffer.from(JSON.stringify(message), 'utf8');
    const header = Buffer.alloc(4);
    header.writeUInt32LE(body.length);
    child.stdin.end(Buffer.concat([header, body]));
  });
}
