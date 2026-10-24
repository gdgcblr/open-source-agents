import { setTimeout as sleep } from 'node:timers/promises';
import { BasePlugin } from '@google/adk';

// Spaces model calls so a run stays under a requests-per-minute limit instead of
// meeting it as 429 errors. A free-tier run measured a limit of 5 requests per
// minute on gemini-3.5-flash, and retrying after a 429 spends requests that
// pacing never sends. One instance is shared by every case in a run.
export class PacingPlugin extends BasePlugin {
  private nextSlot = 0;

  constructor(private readonly gapMs: number) {
    super('pacing');
  }

  override async beforeModelCallback(): Promise<undefined> {
    const now = Date.now();
    const slot = Math.max(now, this.nextSlot);
    this.nextSlot = slot + this.gapMs;
    if (slot > now) await sleep(slot - now);
    return undefined;
  }
}
