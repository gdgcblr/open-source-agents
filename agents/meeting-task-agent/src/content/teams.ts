/**
 * Microsoft Teams Live Caption Observer & Ingestion Content Script
 */

interface TeamsCaptionState {
  lastSpeaker: string;
  lastText: string;
  meetingId: string;
  meetingTitle: string;
}

const state: TeamsCaptionState = {
  lastSpeaker: '',
  lastText: '',
  meetingId: '',
  meetingTitle: '',
};

function getTeamsMeetingId(): string {
  const url = new URL(window.location.href);
  const pathParts = url.pathname.split('/');
  return pathParts[pathParts.length - 1] || 'teams-meeting-session';
}

function getTeamsMeetingTitle(): string {
  const titleElem = document.querySelector('[data-tid="call-title"], [data-tid="meeting-title"]');
  if (titleElem && titleElem.textContent) {
    return titleElem.textContent.trim();
  }
  return document.title.replace('| Microsoft Teams', '').trim() || 'Microsoft Teams Meeting';
}

function injectTeamsStatusBadge(): void {
  if (document.getElementById('meetingmind-teams-badge')) return;

  const badge = document.createElement('div');
  badge.id = 'meetingmind-teams-badge';
  badge.innerHTML = `
    <div style="
      position: fixed;
      bottom: 24px;
      left: 24px;
      z-index: 999999;
      background: #464775;
      color: #ffffff;
      padding: 10px 18px;
      border-radius: 24px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      user-select: none;
    ">
      <span style="
        width: 8px;
        height: 8px;
        background-color: #34d399;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 8px #34d399;
      "></span>
      <span>MeetingMind AI (Teams)</span>
      <span style="
        background: rgba(255,255,255,0.2);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
      ">Open</span>
    </div>
  `;

  badge.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'OPEN_SIDE_PANEL' });
  });

  document.body.appendChild(badge);
}

function processTeamsCaptionNode(node: HTMLElement): void {
  // Microsoft Teams caption container selectors
  const speakerElem = node.querySelector(
    '[data-tid="closed-caption-speaker"], .ui-chat__message__author, .fui-Avatar'
  ) || node.closest('[data-tid="closed-captions-renderer"]')?.querySelector('[data-tid="closed-caption-speaker"]');

  const textElem = node.querySelector(
    '[data-tid="closed-caption-text"], .ui-chat__message__body, .closed-caption-text'
  ) || node;

  const speaker = speakerElem?.textContent?.trim() || state.lastSpeaker || 'Speaker';
  const text = textElem?.textContent?.trim() || '';

  if (!text || text === state.lastText) return;

  let deltaText = text;
  if (speaker === state.lastSpeaker && text.startsWith(state.lastText)) {
    deltaText = text.slice(state.lastText.length).trim();
    if (!deltaText) return;
  }

  state.lastSpeaker = speaker;
  state.lastText = text;

  const chunk = {
    id: `teams_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    meetingId: state.meetingId,
    speaker: speaker,
    text: deltaText,
    timestamp: new Date().toISOString(),
    platform: 'teams' as const,
  };

  chrome.runtime.sendMessage({
    action: 'TRANSCRIPT_CHUNK',
    payload: {
      chunk,
      meetingTitle: state.meetingTitle,
      meetingId: state.meetingId,
    },
  });
}

function initTeamsObserver(): void {
  state.meetingId = getTeamsMeetingId();
  state.meetingTitle = getTeamsMeetingTitle();

  chrome.runtime.sendMessage({
    action: 'MEETING_STARTED',
    payload: {
      meetingId: state.meetingId,
      title: state.meetingTitle,
      platform: 'teams',
    },
  });

  injectTeamsStatusBadge();

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'childList') {
        mutation.addedNodes.forEach((node) => {
          if (node instanceof HTMLElement) {
            if (
              node.matches('[data-tid*="closed-caption"], .closed-captions-container') ||
              node.querySelector('[data-tid*="closed-caption"]')
            ) {
              processTeamsCaptionNode(node);
            }
          }
        });
      } else if (mutation.type === 'characterData' && mutation.target.parentElement) {
        processTeamsCaptionNode(mutation.target.parentElement);
      }
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  console.log('[MeetingMind] Teams Caption Observer initialized for meeting:', state.meetingId);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTeamsObserver);
} else {
  initTeamsObserver();
}

export {};
