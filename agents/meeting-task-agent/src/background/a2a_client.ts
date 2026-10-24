/**
 * Client interface connecting Extension Service Worker to ADK/A2A Multi-Agent Backend & MCP Servers
 */

import {
  ActionItem,
  MeetingSession,
  MeetingSummary,
  TranscriptChunk,
  DriveSaveResult,
  CalendarEventResult,
  EmailNudgeResult,
} from '../shared/types.ts';
import { DEFAULT_SETTINGS, STORAGE_KEYS } from '../shared/constants.ts';

export class A2ABackendClient {
  private static instance: A2ABackendClient;

  private constructor() {}

  public static getInstance(): A2ABackendClient {
    if (!A2ABackendClient.instance) {
      A2ABackendClient.instance = new A2ABackendClient();
    }
    return A2ABackendClient.instance;
  }

  private async getBackendUrl(): Promise<string> {
    const data = await chrome.storage.local.get([STORAGE_KEYS.SETTINGS]);
    return data[STORAGE_KEYS.SETTINGS]?.backendUrl || DEFAULT_SETTINGS.backendUrl;
  }

  /**
   * Request structured meeting summary from Gemma Summarizer Agent
   */
  public async generateSummary(
    meetingTitle: string,
    transcript: TranscriptChunk[]
  ): Promise<MeetingSummary> {
    const baseUrl = await this.getBackendUrl();
    try {
      const response = await fetch(`${baseUrl}/api/agents/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meeting_title: meetingTitle,
          transcript: transcript.map((t) => ({
            speaker: t.speaker,
            text: t.text,
            timestamp: t.timestamp,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`Summarizer agent failed with status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.warn('[A2A Client] Backend unavailable, using local heuristic summarizer:', err);
      // Fallback generator for resilience
      return this.generateLocalFallbackSummary(meetingTitle, transcript);
    }
  }

  /**
   * Request action item extraction per person from Gemma Action Extractor Agent
   */
  public async extractActionItems(
    meetingId: string,
    meetingTitle: string,
    transcript: TranscriptChunk[]
  ): Promise<ActionItem[]> {
    const baseUrl = await this.getBackendUrl();
    try {
      const response = await fetch(`${baseUrl}/api/agents/extract-actions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meeting_id: meetingId,
          meeting_title: meetingTitle,
          transcript: transcript.map((t) => ({
            speaker: t.speaker,
            text: t.text,
            timestamp: t.timestamp,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`Action extractor agent failed with status ${response.status}`);
      }

      const data = await response.json();
      return data.action_items || [];
    } catch (err) {
      console.warn('[A2A Client] Backend unavailable, using local heuristic action extractor:', err);
      return this.extractLocalFallbackActions(meetingId, meetingTitle, transcript);
    }
  }

  /**
   * Sync meeting notes and action items to Google Drive via Drive MCP / REST API
   */
  public async syncToGoogleDrive(
    meeting: MeetingSession,
    authToken: string
  ): Promise<DriveSaveResult> {
    const baseUrl = await this.getBackendUrl();
    try {
      const response = await fetch(`${baseUrl}/api/mcp/drive/save-meeting`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          meeting_id: meeting.id,
          title: meeting.title,
          platform: meeting.platform,
          start_time: meeting.startTime,
          summary: meeting.summary,
          action_items: meeting.actionItems,
          transcript: meeting.transcript,
        }),
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (e) {
      console.log('[A2A Client] Backend Drive MCP route error, falling back to direct Drive API');
    }

    // Direct Google Drive REST API fallback using user's OAuth token
    return this.saveDirectToDrive(meeting, authToken);
  }

  /**
   * Schedule calendar reminder via Google Calendar MCP / REST API
   */
  public async createCalendarReminder(
    task: ActionItem,
    authToken: string
  ): Promise<CalendarEventResult> {
    const baseUrl = await this.getBackendUrl();
    try {
      const response = await fetch(`${baseUrl}/api/mcp/calendar/create-reminder`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          task_id: task.id,
          title: `[MeetingMind Action] ${task.task}`,
          description: `Action item assigned to ${task.owner} from meeting: "${task.meetingTitle}".\nStatus: Pending`,
          deadline: task.deadline,
          owner: task.owner,
          owner_email: task.ownerEmail,
        }),
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (e) {
      console.log('[A2A Client] Backend Calendar MCP error, falling back to direct Calendar API');
    }

    return this.createDirectCalendarEvent(task, authToken);
  }

  /**
   * Trigger email nudge for missing deadline or overdue task via Gmail MCP
   */
  public async sendEmailNudge(
    task: ActionItem,
    authToken: string,
    reason: 'missing_deadline' | 'overdue' | 'approaching'
  ): Promise<EmailNudgeResult> {
    const baseUrl = await this.getBackendUrl();
    try {
      const response = await fetch(`${baseUrl}/api/mcp/gmail/send-nudge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          task_id: task.id,
          task_title: task.task,
          owner: task.owner,
          owner_email: task.ownerEmail,
          meeting_title: task.meetingTitle,
          reason,
          deadline: task.deadline,
        }),
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (e) {
      console.log('[A2A Client] Backend Gmail MCP error, falling back to direct Gmail API');
    }

    return this.sendDirectGmailNudge(task, authToken, reason);
  }

  // --- Fallback & Direct Google API Implementations ---

  private async saveDirectToDrive(
    meeting: MeetingSession,
    authToken: string
  ): Promise<DriveSaveResult> {
    // 1. Find or create 'MeetingMind' folder
    let folderId = await this.getOrCreateFolder('MeetingMind', authToken);

    // 2. Format meeting notes in Markdown
    const markdown = this.buildMeetingMarkdown(meeting);
    const fileName = `${meeting.title.replace(/[/\\?%*:|"<>]/g, '-')}_Notes.md`;

    // 3. Upload file to Drive
    const metadata = {
      name: fileName,
      parents: [folderId],
      mimeType: 'text/markdown',
    };

    const boundary = '-------314159265358979323846';
    const delimiter = `\r\n--${boundary}\r\n`;
    const closeDelimiter = `\r\n--${boundary}--`;

    const multipartRequestBody =
      delimiter +
      'Content-Type: application/json; charset=UTF-8\r\n\r\n' +
      JSON.stringify(metadata) +
      delimiter +
      'Content-Type: text/markdown\r\n\r\n' +
      markdown +
      closeDelimiter;

    const response = await fetch(
      'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink',
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body: multipartRequestBody,
      }
    );

    if (!response.ok) {
      throw new Error(`Drive file creation failed with ${response.status}`);
    }

    const data = await response.json();
    return {
      fileId: data.id,
      webViewLink: data.webViewLink,
      fileName,
    };
  }

  private async getOrCreateFolder(folderName: string, authToken: string): Promise<string> {
    const q = encodeURIComponent(`name = '${folderName}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`);
    const searchRes = await fetch(`https://www.googleapis.com/drive/v3/files?q=${q}&fields=files(id,name)`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    const data = await searchRes.json();
    if (data.files && data.files.length > 0) {
      return data.files[0].id;
    }

    // Create folder
    const createRes = await fetch('https://www.googleapis.com/drive/v3/files', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: folderName,
        mimeType: 'application/vnd.google-apps.folder',
      }),
    });
    const folder = await createRes.json();
    return folder.id;
  }

  private buildMeetingMarkdown(meeting: MeetingSession): string {
    const summary = meeting.summary;
    const actions = meeting.actionItems;

    let md = `# ${meeting.title}\n\n`;
    md += `*Platform*: ${meeting.platform.toUpperCase()} | *Date*: ${new Date(meeting.startTime).toLocaleString()}\n\n`;

    if (summary) {
      md += `## Executive Summary\n${summary.overview}\n\n`;
      md += `### Key Highlights\n`;
      summary.keyPoints.forEach((kp) => (md += `- ${kp}\n`));
      md += `\n### Key Decisions\n`;
      summary.decisions.forEach((d) => (md += `- ${d}\n`));
      md += `\n`;
    }

    md += `## Action Items (To-Do List)\n\n`;
    if (actions.length === 0) {
      md += `_No action items recorded for this meeting._\n\n`;
    } else {
      actions.forEach((a) => {
        const check = a.status === 'completed' ? '[x]' : '[ ]';
        const deadline = a.deadline ? new Date(a.deadline).toLocaleDateString() : 'No deadline set';
        md += `- ${check} **${a.owner}**: ${a.task} *(Due: ${deadline})* - Status: ${a.status}\n`;
      });
      md += `\n`;
    }

    md += `## Full Transcript\n\n`;
    meeting.transcript.forEach((t) => {
      const time = new Date(t.timestamp).toLocaleTimeString();
      md += `> **[${time}] ${t.speaker}**: ${t.text}\n\n`;
    });

    return md;
  }

  private async createDirectCalendarEvent(
    task: ActionItem,
    authToken: string
  ): Promise<CalendarEventResult> {
    const deadlineDate = task.deadline ? new Date(task.deadline) : new Date(Date.now() + 24 * 3600 * 1000);
    const endDate = new Date(deadlineDate.getTime() + 30 * 60 * 1000);

    const event = {
      summary: `[MeetingMind] Action: ${task.task}`,
      description: `Action item assigned to ${task.owner} from meeting "${task.meetingTitle}".\nStatus: ${task.status}`,
      start: { dateTime: deadlineDate.toISOString() },
      end: { dateTime: endDate.toISOString() },
      reminders: {
        useDefault: false,
        overrides: [
          { method: 'popup', minutes: 1440 }, // 24 hours prior
          { method: 'popup', minutes: 120 },  // 2 hours prior
          { method: 'email', minutes: 60 },   // 1 hour prior
        ],
      },
    };

    const res = await fetch('https://www.googleapis.com/calendar/v3/calendars/primary/events', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(event),
    });

    const data = await res.json();
    return {
      eventId: data.id,
      htmlLink: data.htmlLink,
      summary: event.summary,
      start: deadlineDate.toISOString(),
    };
  }

  private async sendDirectGmailNudge(
    task: ActionItem,
    authToken: string,
    reason: string
  ): Promise<EmailNudgeResult> {
    const userProfile = (await chrome.storage.local.get([STORAGE_KEYS.USER_PROFILE]))[STORAGE_KEYS.USER_PROFILE];
    const recipient = task.ownerEmail || userProfile?.email;
    if (!recipient) {
      throw new Error('No recipient email available for nudge');
    }

    let subject = `Action Item Reminder: "${task.task.substring(0, 40)}..."`;
    let body = `Hi ${task.owner},\n\n`;

    if (reason === 'missing_deadline') {
      subject = `[Action Required] Set deadline for: "${task.task.substring(0, 40)}"`;
      body += `During the meeting "${task.meetingTitle}", the following action item was recorded for you without a specific deadline:\n\n`;
      body += `Task: "${task.task}"\n\n`;
      body += `Please open the MeetingMind extension or reply to set a target completion date so a calendar reminder can be created.\n\n`;
    } else {
      body += `This is a friendly reminder regarding your pending action item from "${task.meetingTitle}":\n\n`;
      body += `Task: "${task.task}"\n`;
      body += `Deadline: ${task.deadline ? new Date(task.deadline).toLocaleString() : 'Not set'}\n\n`;
      body += `Please mark it completed in your MeetingMind extension once done.\n\n`;
    }

    body += `Best regards,\nMeetingMind AI Agent`;

    const rawMessage = [
      `To: ${recipient}`,
      `Subject: ${subject}`,
      `Content-Type: text/plain; charset=utf-8`,
      '',
      body,
    ].join('\r\n');

    // Base64url encode
    const encodedMessage = btoa(unescape(encodeURIComponent(rawMessage)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    const res = await fetch('https://www.googleapis.com/gmail/v1/users/me/messages/send', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ raw: encodedMessage }),
    });

    const data = await res.json();
    return {
      messageId: data.id,
      recipientEmail: recipient,
      sentAt: new Date().toISOString(),
    };
  }

  private generateLocalFallbackSummary(
    meetingTitle: string,
    transcript: TranscriptChunk[]
  ): MeetingSummary {
    const speakers = Array.from(new Set(transcript.map((t) => t.speaker)));
    const sampleSentences = transcript
      .map((t) => t.text)
      .join(' ')
      .split(/[.?!]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 20);

    return {
      meetingId: transcript[0]?.meetingId || 'local-meeting',
      title: meetingTitle,
      overview: `Discussion covered key operational goals and action items among ${speakers.join(', ')}.`,
      keyPoints: sampleSentences.slice(0, 4),
      decisions: ['Agreed on schedule and delegated responsibilities to respective owners.'],
      topics: [
        {
          topic: 'General Discussion',
          discussion: sampleSentences.slice(0, 2).join('. ') || 'Discussion recorded in transcript.',
        },
      ],
      generatedAt: new Date().toISOString(),
    };
  }

  private extractLocalFallbackActions(
    meetingId: string,
    meetingTitle: string,
    transcript: TranscriptChunk[]
  ): ActionItem[] {
    const items: ActionItem[] = [];
    const actionKeywords = /\b(will|should|need to|must|action|assigned to|takes care of|follow up|prepare|finalize|send|schedule|deadline)\b/i;

    for (const chunk of transcript) {
      if (actionKeywords.test(chunk.text)) {
        items.push({
          id: `task_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
          meetingId,
          meetingTitle,
          owner: chunk.speaker,
          task: chunk.text.trim(),
          deadline: null, // Will prompt user
          priority: 'medium',
          status: 'pending',
          nudgeCount: 0,
          createdAt: new Date().toISOString(),
        });
      }
    }

    return items;
  }
}

