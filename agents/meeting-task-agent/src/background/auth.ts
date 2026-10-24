/**
 * Google Authentication Manager using Chrome Identity API (OAuth2)
 */

import { UserProfile } from '../shared/types.ts';
import { STORAGE_KEYS as KEYS } from '../shared/constants.ts';

export class GoogleAuthManager {
  private static instance: GoogleAuthManager;

  private constructor() {}

  public static getInstance(): GoogleAuthManager {
    if (!GoogleAuthManager.instance) {
      GoogleAuthManager.instance = new GoogleAuthManager();
    }
    return GoogleAuthManager.instance;
  }

  /**
   * Acquire OAuth2 access token interactively or silently
   */
  public async getAuthToken(interactive: boolean = false): Promise<string> {
    return new Promise((resolve, reject) => {
      chrome.identity.getAuthToken({ interactive }, (token) => {
        if (chrome.runtime.lastError) {
          return reject(new Error(chrome.runtime.lastError.message));
        }
        if (!token) {
          return reject(new Error('Failed to acquire Google auth token'));
        }
        resolve(token);
      });
    });
  }

  /**
   * Fetch user profile from Google UserInfo API
   */
  public async fetchUserProfile(token: string): Promise<UserProfile> {
    try {
      const response = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`UserInfo API returned ${response.status}`);
      }

      const data = await response.json();
      const profile: UserProfile = {
        email: data.email,
        name: data.name || data.email.split('@')[0],
        picture: data.picture,
        isSignedIn: true,
      };

      await chrome.storage.local.set({
        [KEYS.USER_PROFILE]: profile,
        [KEYS.AUTH_TOKEN]: token,
      });

      return profile;
    } catch (err) {
      console.error('[MeetingMind Auth] Error fetching user profile:', err);
      throw err;
    }
  }

  /**
   * Sign out and clear cached token
   */
  public async signOut(): Promise<void> {
    const data = await chrome.storage.local.get([KEYS.AUTH_TOKEN]);
    const token = data[KEYS.AUTH_TOKEN];

    if (token) {
      await new Promise<void>((resolve) => {
        chrome.identity.removeCachedAuthToken({ token }, () => {
          resolve();
        });
      });

      // Revoke token with Google endpoint
      try {
        await fetch(`https://accounts.google.com/o/oauth2/revoke?token=${token}`);
      } catch (e) {
        console.warn('[MeetingMind Auth] Token revocation failed (may already be expired):', e);
      }
    }

    await chrome.storage.local.remove([KEYS.AUTH_TOKEN]);
    await chrome.storage.local.set({
      [KEYS.USER_PROFILE]: {
        email: '',
        name: '',
        isSignedIn: false,
      },
    });
  }

  /**
   * Check current authentication state
   */
  public async getCurrentProfile(): Promise<UserProfile> {
    const data = await chrome.storage.local.get([KEYS.USER_PROFILE]);
    return (
      data[KEYS.USER_PROFILE] || {
        email: '',
        name: '',
        isSignedIn: false,
      }
    );
  }
}
