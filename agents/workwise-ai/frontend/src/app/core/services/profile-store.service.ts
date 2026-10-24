import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { UserProfileResponse } from '../models';
import { ProfileService } from './profile.service';

/**
 * Holds the "active profile" for the currently selected demo persona. Each demo persona
 * (see CurrentUserService) owns exactly one seeded profile, so this store simply loads
 * "my profiles" (scoped server-side to the X-Demo-User-Id header) and keeps the first one.
 */
@Injectable({ providedIn: 'root' })
export class ProfileStore {
  private readonly profileService = inject(ProfileService);

  private readonly profileSignal = signal<UserProfileResponse | null>(null);
  private readonly loadingSignal = signal(false);
  private readonly loadedSignal = signal(false);

  readonly profile = this.profileSignal.asReadonly();
  readonly loading = this.loadingSignal.asReadonly();
  readonly hasProfile = computed(() => this.profileSignal() !== null);

  async load(): Promise<UserProfileResponse | null> {
    this.loadingSignal.set(true);
    try {
      const profiles = await firstValueFrom(this.profileService.listMine());
      const profile = profiles.length > 0 ? profiles[0] : null;
      this.profileSignal.set(profile);
      this.loadedSignal.set(true);
      return profile;
    } finally {
      this.loadingSignal.set(false);
    }
  }

  set(profile: UserProfileResponse): void {
    this.profileSignal.set(profile);
  }

  clear(): void {
    this.profileSignal.set(null);
    this.loadedSignal.set(false);
  }
}
