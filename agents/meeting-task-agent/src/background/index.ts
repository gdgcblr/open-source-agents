/**
 * Background Service Worker Entry Point for MeetingMind
 */

import {
  ActionItem,
  MeetingSession,
} from '../shared/types.ts';
import { STORAGE_KEYS } from '../shared/constants.ts';
import { GoogleAuthManager } from './auth.ts';
import { A2ABackendClient } from './a2a_client.ts';
import { AlarmReminderDaemon } from './alarms.ts';

const authManager = GoogleAuthManager.getInstance();
const a2aClient = A2ABackendClient.getInstance();
const alarmDaemon = AlarmReminderDaemon.getInstance();

// Initialize alarms on installation/startup
chrome.runtime.onInstalled.addListener(() => {
  alarmDaemon.init();
  console.log('[MeetingMind] Service Worker installed and alarms initialized');
});

chrome.runtime.onStartup.addListener(() => {
  alarmDaemon.init();
});

// Configure Side Panel behavior
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch((error) => {
  console.error('[MeetingMind] Side panel setup error:', error);
});

// Message Dispatcher
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const { action, payload } = message;

  (async () => {
    try {
      switch (action) {
        case 'OPEN_SIDE_PANEL': {
          if (_sender.tab?.windowId) {
            await chrome.sidePanel.open({ windowId: _sender.tab.windowId });
          }
          sendResponse({ success: true });
          break;
        }

        case 'SIGN_IN_GOOGLE': {
          const token = await authManager.getAuthToken(true);
          const profile = await authManager.fetchUserProfile(token);
          sendResponse({ success: true, profile, token });
          break;
        }

        case 'SIGN_OUT_GOOGLE': {
          await authManager.signOut();
          sendResponse({ success: true });
          break;
        }

        case 'MEETING_STARTED': {
          const { meetingId, title, platform } = payload;
          const session: MeetingSession = {
            id: meetingId,
            title,
            platform,
            startTime: new Date().toISOString(),
            isActive: true,
            participants: [],
            transcript: [],
            actionItems: [],
          };
          await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });
          sendResponse({ success: true, session });
          break;
        }

        case 'TRANSCRIPT_CHUNK': {
          const { chunk, meetingTitle, meetingId } = payload;
          const data = await chrome.storage.local.get([STORAGE_KEYS.ACTIVE_MEETING]);
          let session: MeetingSession = data[STORAGE_KEYS.ACTIVE_MEETING];

          if (!session || session.id !== meetingId) {
            session = {
              id: meetingId,
              title: meetingTitle,
              platform: chunk.platform,
              startTime: new Date().toISOString(),
              isActive: true,
              participants: [],
              transcript: [],
              actionItems: [],
            };
          }

          if (!session.participants.includes(chunk.speaker)) {
            session.participants.push(chunk.speaker);
          }

          session.transcript.push(chunk);
          await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });
          sendResponse({ success: true, transcriptLength: session.transcript.length });
          break;
        }

        case 'GENERATE_SUMMARY': {
          const data = await chrome.storage.local.get([STORAGE_KEYS.ACTIVE_MEETING]);
          const session: MeetingSession = data[STORAGE_KEYS.ACTIVE_MEETING];
          if (!session || session.transcript.length === 0) {
            return sendResponse({ success: false, error: 'No transcript recorded yet' });
          }

          const summary = await a2aClient.generateSummary(session.title, session.transcript);
          session.summary = summary;
          await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });
          sendResponse({ success: true, summary });
          break;
        }

        case 'EXTRACT_ACTIONS': {
          const data = await chrome.storage.local.get([
            STORAGE_KEYS.ACTIVE_MEETING,
            STORAGE_KEYS.TASKS,
          ]);
          const session: MeetingSession = data[STORAGE_KEYS.ACTIVE_MEETING];
          if (!session || session.transcript.length === 0) {
            return sendResponse({ success: false, error: 'No transcript recorded yet' });
          }

          const newActions = await a2aClient.extractActionItems(
            session.id,
            session.title,
            session.transcript
          );

          session.actionItems = newActions;
          await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });

          // Merge into global task list
          const existingTasks: ActionItem[] = data[STORAGE_KEYS.TASKS] || [];
          const existingIds = new Set(existingTasks.map((t) => t.id));
          const updatedTasks = [...existingTasks];

          for (const item of newActions) {
            if (!existingIds.has(item.id)) {
              updatedTasks.push(item);
            }
          }

          await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: updatedTasks });
          alarmDaemon.handleTaskReminderCheck(); // Update badge

          sendResponse({ success: true, actionItems: newActions });
          break;
        }

        case 'UPDATE_TASK': {
          const { taskId, updates } = payload as { taskId: string; updates: Partial<ActionItem> };
          const data = await chrome.storage.local.get([
            STORAGE_KEYS.TASKS,
            STORAGE_KEYS.ACTIVE_MEETING,
          ]);
          const tasks: ActionItem[] = data[STORAGE_KEYS.TASKS] || [];
          let targetTask: ActionItem | null = null;

          const updatedTasks = tasks.map((t) => {
            if (t.id === taskId) {
              const updated = { ...t, ...updates };
              if (updates.status === 'completed' && !t.completedAt) {
                updated.completedAt = new Date().toISOString();
              }
              targetTask = updated;
              return updated;
            }
            return t;
          });

          await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: updatedTasks });

          // Also update in active meeting if present
          const session: MeetingSession = data[STORAGE_KEYS.ACTIVE_MEETING];
          if (session && session.actionItems) {
            session.actionItems = session.actionItems.map((t) =>
              t.id === taskId ? { ...t, ...updates } : t
            );
            await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });
          }

          // If deadline was just set or updated, create/update Google Calendar event
          const finalTask = targetTask as ActionItem | null;
          if (updates.deadline && finalTask) {
            try {
              const token = await authManager.getAuthToken(false);
              const calRes = await a2aClient.createCalendarReminder(finalTask, token);
              finalTask.calendarEventId = calRes.eventId;
              finalTask.calendarEventUrl = calRes.htmlLink;
              await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: updatedTasks });
            } catch (calErr) {
              console.warn('[MeetingMind] Calendar event creation failed or auth required:', calErr);
            }
          }

          alarmDaemon.handleTaskReminderCheck(); // Recalculate badge and alerts
          sendResponse({ success: true, task: targetTask });
          break;
        }

        case 'ADD_MANUAL_TASK': {
          const { task, owner, deadline, priority, meetingTitle } = payload;
          const newTask: ActionItem = {
            id: `manual_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
            meetingId: 'manual',
            meetingTitle: meetingTitle || 'Ad-hoc Task',
            owner: owner || 'Me',
            task,
            deadline: deadline || null,
            priority: priority || 'medium',
            status: 'pending',
            nudgeCount: 0,
            createdAt: new Date().toISOString(),
            isManual: true,
          };

          const data = await chrome.storage.local.get([STORAGE_KEYS.TASKS]);
          const tasks: ActionItem[] = data[STORAGE_KEYS.TASKS] || [];
          tasks.unshift(newTask);
          await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: tasks });

          // Sync to calendar if deadline provided
          if (deadline) {
            try {
              const token = await authManager.getAuthToken(false);
              const calRes = await a2aClient.createCalendarReminder(newTask, token);
              newTask.calendarEventId = calRes.eventId;
              newTask.calendarEventUrl = calRes.htmlLink;
              await chrome.storage.local.set({ [STORAGE_KEYS.TASKS]: tasks });
            } catch (err) {
              console.log('[MeetingMind] Manual task saved, calendar sync optional:', err);
            }
          }

          alarmDaemon.handleTaskReminderCheck();
          sendResponse({ success: true, task: newTask });
          break;
        }

        case 'TRIGGER_SYNC_DRIVE': {
          const data = await chrome.storage.local.get([STORAGE_KEYS.ACTIVE_MEETING]);
          const session: MeetingSession = data[STORAGE_KEYS.ACTIVE_MEETING];
          if (!session) {
            return sendResponse({ success: false, error: 'No active meeting to sync' });
          }

          const token = await authManager.getAuthToken(true);
          const driveRes = await a2aClient.syncToGoogleDrive(session, token);

          session.driveDocId = driveRes.fileId;
          session.driveUrl = driveRes.webViewLink;
          await chrome.storage.local.set({ [STORAGE_KEYS.ACTIVE_MEETING]: session });

          sendResponse({ success: true, driveUrl: driveRes.webViewLink });
          break;
        }

        case 'GET_STATE': {
          const data = await chrome.storage.local.get([
            STORAGE_KEYS.ACTIVE_MEETING,
            STORAGE_KEYS.TASKS,
            STORAGE_KEYS.USER_PROFILE,
            STORAGE_KEYS.SETTINGS,
          ]);
          sendResponse({ success: true, data });
          break;
        }

        default:
          sendResponse({ success: false, error: `Unknown action: ${action}` });
      }
    } catch (err: any) {
      console.error(`[MeetingMind Background] Error processing ${action}:`, err);
      sendResponse({ success: false, error: err.message || 'Internal error' });
    }
  })();

  return true; // Keep message channel open for async response
});
