import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'workwise.demoUserId';
const DEFAULT_USER_ID = 'demo-textile-trader';

/** Known demo personas seeded by V2__seed_demo_data.sql, offered as a switcher in the UI so the
 * relevance engine can be shown working for more than one occupation. */
export const DEMO_PERSONAS = [
  { userId: 'demo-textile-trader', label: 'Textile Trader (Surat)', profileId: '00000000-0000-0000-0000-000000000010' },
  { userId: 'demo-software-engineer', label: 'Software Engineer (Bengaluru)', profileId: '00000000-0000-0000-0000-000000000011' }
];

/**
 * Holds the "current demo user id" sent as the X-Demo-User-Id header on every request. This
 * mirrors the backend's documented prototype authentication mechanism (see
 * com.workwise.ai.common.auth.DemoUserFilter) and is not real authentication.
 */
@Injectable({ providedIn: 'root' })
export class CurrentUserService {
  private readonly userIdSignal = signal<string>(localStorage.getItem(STORAGE_KEY) ?? DEFAULT_USER_ID);

  readonly userId = this.userIdSignal.asReadonly();

  setUserId(userId: string): void {
    localStorage.setItem(STORAGE_KEY, userId);
    this.userIdSignal.set(userId);
  }

  get currentPersona() {
    return DEMO_PERSONAS.find((p) => p.userId === this.userIdSignal()) ?? DEMO_PERSONAS[0];
  }
}
