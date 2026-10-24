/**
 * Persistent Alarms & Nudge Daemon for MeetingMind
 * Manages recurring reminders, desktop notifications, and email nudges.
 */

import { ActionItem } from '../shared/types.ts';
import { ALARM_NAMES, DEFAULT_SETTINGS, STORAGE_KEYS } from '../shared/constants.ts';
import { GoogleAuthManager } from './auth.ts';
import { A2ABackendClient } from './a2a_client.ts';

export class AlarmReminderDaemon {
  private static instance: AlarmReminderDaemon;

  private constructor() {}

  public static getInstance(): AlarmReminderDaemon {
    if (!AlarmReminderDaemon.instance) {
      AlarmReminderDaemon.instance = new AlarmReminderDaemon();
    }
    return AlarmReminderDaemon.instance;
  }

  /**
   * Initialize alarms
   */
  public init(): void {
    chrome.alarms.create(ALARM_NAMES.TASK_REMINDER_CHECK, {
      periodInMinutes: 15, // Check reminders every 15 minutes
    });

    chrome.alarms.create(ALARM_NAMES.NUDGE_CHECK, {
      periodInMinutes: 30, // Check email nudges every 30 minutes
    });

    chrome.alarms.onAlarm.addListener(async (alarm) => {
      if (alarm.name === ALARM_NAMES.TASK_REMINDER_CHECK) {
        await this.handleTaskReminderCheck();
      } else if (alarm.name === ALARM_NAMES.NUDGE_CHECK) {
        await this.handleNudgeCheck();
      }
    });

    // Also run an immediate check on startup
    this.handleTaskReminderCheck();
  }

  /**
   * Handle recurring task reminders (Feature 6: keep showing until completed, cancelled, or rescheduled)
   */
  public async handleTaskReminderCheck(): Promise<void> {
    const data = await chrome.storage.local.get([STORAGE_KEYS.TASKS]);
    const tasks: ActionItem[] = data[STORAGE_KEYS.TASKS] || [];

    const pendingTasks = tasks.filter((t) => t.status === 'pending');

    // Update extension badge
    if (pendingTasks.length > 0) {
      chrome.action.setBadgeText({ text: String(pendingTasks.length) });
      chrome.action.setBadgeBackgroundColor({ color: '#ef4444' }); // Red badge
    } else {
      chrome.action.setBadgeText({ text: '' });
    }

    const now = Date.now();

    for (const task of pendingTasks) {
      // If deadline is set, check if reminder is due
      if (task.deadline) {
        const deadlineTime = new Date(task.deadline).getTime();
        const diffMs = deadlineTime - now;
        const diffHours = diffMs / (1000 * 60 * 60);

        // If deadline is within 24 hours, or overdue
        if (diffHours <= 24) {
          const statusText = diffHours < 0 ? 'OVERDUE' : `due in ${Math.round(diffHours)}h`;

          chrome.notifications.create(`task_reminder_${task.id}_${Date.now()}`, {
            type: 'basic',
            iconUrl: 'icons/icon128.png',
            title: `MeetingMind Reminder: Task ${statusText}`,
            message: `"${task.task}" assigned to ${task.owner} (${task.meetingTitle})`,
            priority: 2,
            requireInteraction: true, // Remains on screen until dismissed or acted upon
          });
        }
      }
    }
  }

  /**
   * Handle automated nudges (Feature 4: Nudges via email if deadline/action item is not set)
   */
  public async handleNudgeCheck(): Promise<void> {
    const settingsData = await chrome.storage.local.get([STORAGE_KEYS.SETTINGS]);
    const settings = settingsData[STORAGE_KEYS.SETTINGS] || DEFAULT_SETTINGS;

    if (!settings.emailNudgesEnabled) return;

    const auth = GoogleAuthManager.getInstance();
    const profile = await auth.getCurrentProfile();
    if (!profile.isSignedIn) return;

    let token: string;
    try {
      token = await auth.getAuthToken(false);
    } catch {
      return; // Token expired or not available silently
    }

    const tasksData = await chrome.storage.local.get([STORAGE_KEYS.TASKS]);
    const tasks: ActionItem[] = tasksData[STORAGE_KEYS.TASKS] || [];
    let tasksUpdated = false;

    const now = Date.now();
    const gracePeriodMs = (settings.nudgeGracePeriodHours || 2) * 60 * 60 * 1000;

    for (const task of tasks) {
      if (task.status !== 'pending') continue;

      // 1. Missing deadline nudge
      if (!task.deadline) {
        const taskAgeMs = now - new Date(task.createdAt).getTime();

        // If task was created > gracePeriodMs ago and hasn't been nudged in the last 24h
        const lastNudgeMs = task.lastNudgedAt ? new Date(task.lastNudgedAt).getTime() : 0;
        const timeSinceLastNudge = now - lastNudgeMs;

        if (taskAgeMs >= gracePeriodMs && (task.nudgeCount === 0 || timeSinceLastNudge > 24 * 3600 * 1000)) {
          try {
            await A2ABackendClient.getInstance().sendEmailNudge(task, token, 'missing_deadline');
            task.nudgeCount += 1;
            task.lastNudgedAt = new Date().toISOString();
            tasksUpdated = true;
            console.log(`[MeetingMind Nudge] Sent missing deadline nudge for task ${task.id}`);
          } catch (err) {
            console.warn(`[MeetingMind Nudge] Failed sending missing deadline email for task ${task.id}:`, err);
          }
        }
      }

      // 2. Overdue task nudge
      if (task.deadline) {
        const deadlineTime = new Date(task.deadline).getTime();
        if (now > deadlineTime) {
          const lastNudgeMs = task.lastNudgedAt ? new Date(task.lastNudgedAt).getTime() : 0;
          if (now - lastNudgeMs > 24 * 3600 * 1000) {
            try {
              await A2ABackendClient.getInstance().sendEmailNudge(task, token, 'overdue');
              task.nudgeCount += 1;
              task.lastNudgedAt = new Date().toISOString();
              tasksUpdated = true;
            } catch (err) {
              console.warn(`[MeetingMind Nudge] Failed sending overdue email for task ${task.id}:`, err);
            }
          }
        }
      }
    }

    if (tasksUpdated) {
      await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: tasks });
    }
  }
}

