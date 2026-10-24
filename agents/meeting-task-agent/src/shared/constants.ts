/**
 * Application constants and default configurations for MeetingMind
 */

export const STORAGE_KEYS = {
  ACTIVE_MEETING: 'meetingmind_active_meeting',
  PAST_MEETINGS: 'meetingmind_past_meetings',
  TASKS: 'meetingmind_tasks',
  USER_PROFILE: 'meetingmind_user_profile',
  SETTINGS: 'meetingmind_settings',
  AUTH_TOKEN: 'meetingmind_auth_token',
} as const;

export const ALARM_NAMES = {
  TASK_REMINDER_CHECK: 'meetingmind_task_reminder_check',
  NUDGE_CHECK: 'meetingmind_nudge_check',
} as const;

export const OAUTH_SCOPES = [
  'https://www.googleapis.com/auth/userinfo.email',
  'https://www.googleapis.com/auth/userinfo.profile',
  'https://www.googleapis.com/auth/drive.file',
  'https://www.googleapis.com/auth/calendar.events',
  'https://www.googleapis.com/auth/gmail.send',
];

export interface AppSettings {
  backendUrl: string;
  modelName: string;
  autoSaveToDrive: boolean;
  autoCalendarSync: boolean;
  emailNudgesEnabled: boolean;
  nudgeGracePeriodHours: number; // Hours to wait before sending first nudge if deadline missing
  reminderIntervalMinutes: number; // Alarm check interval
  defaultDriveFolder: string;
}

export const DEFAULT_SETTINGS: AppSettings = {
  backendUrl: 'http://localhost:8000',
  modelName: 'gemma2:9b',
  autoSaveToDrive: true,
  autoCalendarSync: true,
  emailNudgesEnabled: true,
  nudgeGracePeriodHours: 2,
  reminderIntervalMinutes: 30,
  defaultDriveFolder: 'MeetingMind',
};

