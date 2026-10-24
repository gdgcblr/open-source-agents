/**
 * Core data types for MeetingMind AI Agent
 */

export type PlatformType = 'meet' | 'teams' | 'zoom' | 'other';

export type TaskStatus = 'pending' | 'completed' | 'cancelled' | 'rescheduled';

export interface TranscriptChunk {
  id: string;
  meetingId: string;
  speaker: string;
  text: string;
  timestamp: string; // ISO 8601
  platform: PlatformType;
}

export interface ActionItem {
  id: string;
  meetingId: string;
  meetingTitle: string;
  owner: string;
  ownerEmail?: string;
  task: string;
  deadline: string | null; // ISO 8601 string or null if not yet determined
  priority: 'low' | 'medium' | 'high';
  status: TaskStatus;
  calendarEventId?: string;
  calendarEventUrl?: string;
  lastNudgedAt?: string;
  nudgeCount: number;
  createdAt: string;
  completedAt?: string;
  isManual?: boolean;
}

export interface MeetingSummary {
  meetingId: string;
  title: string;
  overview: string;
  keyPoints: string[];
  decisions: string[];
  topics: Array<{
    topic: string;
    discussion: string;
  }>;
  generatedAt: string;
}

export interface MeetingSession {
  id: string;
  title: string;
  platform: PlatformType;
  startTime: string;
  endTime?: string;
  isActive: boolean;
  participants: string[];
  transcript: TranscriptChunk[];
  summary?: MeetingSummary;
  actionItems: ActionItem[];
  driveDocId?: string;
  driveUrl?: string;
}

export interface UserProfile {
  email: string;
  name: string;
  picture?: string;
  isSignedIn: boolean;
}

export interface DriveSaveResult {
  fileId: string;
  webViewLink: string;
  fileName: string;
}

export interface CalendarEventResult {
  eventId: string;
  htmlLink: string;
  summary: string;
  start: string;
}

export interface EmailNudgeResult {
  messageId: string;
  recipientEmail: string;
  sentAt: string;
}

// Agent-to-Agent (A2A) Message Payloads
export type A2AAgentType =
  | 'ingestion-agent'
  | 'summarizer-agent'
  | 'action-extractor-agent'
  | 'scheduler-agent'
  | 'nudge-agent';

export interface A2AMessage<T = any> {
  id: string;
  sourceAgent: A2AAgentType | 'extension-client';
  targetAgent: A2AAgentType | 'extension-client' | 'broadcast';
  action: string;
  timestamp: string;
  data: T;
}

