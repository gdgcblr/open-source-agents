/**
 * Google Meet Live Caption Observer & Ingestion Content Script
 */

interface MeetCaptionState {
  lastSpeaker: string;
  lastText: string;
  meetingId: string;
  meetingTitle: string;
  isActive: boolean;
}

const state: MeetCaptionState = {
  lastSpeaker: '',
  lastText: '',
  meetingId: '',
  meetingTitle: '',
  isActive: true,
};

function getMeetingId(): string {
  const pathname = window.location.pathname.replace(/^\//, '');
  return pathname.split('?')[0] || 'google-meet-session';
}

function getMeetingTitle(): string {
  // Try extracting from Meet DOM
  const titleElem = document.querySelector('[data-meeting-title]');
  if (titleElem && titleElem.textContent) {
    return titleElem.textContent.trim();
  }
  return document.title.replace('- Google Meet', '').trim() || `Meeting ${getMeetingId()}`;
}

function injectFloatingStatusBadge(): void {
  if (document.getElementById('meetingmind-meet-badge')) return;

  const badge = document.createElement('div');
  badge.id = 'meetingmind-meet-badge';
  badge.innerHTML = `
    <div style="
      position: fixed;
      bottom: 20px;
      left: 20px;
      z-index: 999999;
      background: linear-gradient(135deg, #1e293b, #0f172a);
      color: #f8fafc;
      padding: 10px 16px;
      border-radius: 9999px;
      box-shadow: 0 10px 25px -5px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.1);
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 13px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      user-select: none;
      transition: all 0.2s ease;
    ">
      <span style="
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 8px #10b981;
      "></span>
      <span>MeetingMind AI Active</span>
      <span style="
        background: rgba(255,255,255,0.15);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
      ">Open Notes</span>
    </div>
  `;

  badge.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'OPEN_SIDE_PANEL' });
  });

  document.body.appendChild(badge);
}

function processCaptionNode(node: HTMLElement): void {
  // Selector targets common Google Meet caption elements
  // Google Meet structure:
  // Container: [jsname="YSvyTc"]
  // Speaker: [class*="zs7s8d"], [class*="Tbmif"]
  // Text: [class*="VbkSUe"], [class*="yg7Ot"], [class*="CNusmb"]

  const speakerElem = node.querySelector(
    '[class*="zs7s8d"], [class*="Tbmif"], [class*="poVWob"]'
  ) || node.closest('[jsname="YSvyTc"]')?.querySelector('[class*="zs7s8d"]');

  const textElem = node.querySelector(
    '[class*="VbkSUe"], [class*="yg7Ot"], [class*="CNusmb"]'
  ) || node;

  const speaker = speakerElem?.textContent?.trim() || state.lastSpeaker || 'Speaker';
  const text = textElem?.textContent?.trim() || '';

  if (!text || text === state.lastText) {
    return;
  }

  // Check if current text is just an expansion of previous text for the same speaker
  let deltaText = text;
  if (speaker === state.lastSpeaker && text.startsWith(state.lastText)) {
    deltaText = text.slice(state.lastText.length).trim();
    if (!deltaText) return;
  }

  state.lastSpeaker = speaker;
  state.lastText = text;

  // Send chunk to background service worker
  const chunk = {
    id: `chunk_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    meetingId: state.meetingId,
    speaker: speaker,
    text: deltaText,
    timestamp: new Date().toISOString(),
    platform: 'meet' as const,
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

function initCaptionObserver(): void {
  state.meetingId = getMeetingId();
  state.meetingTitle = getMeetingTitle();

  // Notify background that meeting has started
  chrome.runtime.sendMessage({
    action: 'MEETING_STARTED',
    payload: {
      meetingId: state.meetingId,
      title: state.meetingTitle,
      platform: 'meet',
    },
  });

  injectFloatingStatusBadge();

  // Observe caption mutations
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'childList') {
        mutation.addedNodes.forEach((node) => {
          if (node instanceof HTMLElement) {
            // Check if node is part of caption container
            if (
              node.matches('[jsname="YSvyTc"], [class*="VbkSUe"], [class*="CNusmb"]') ||
              node.querySelector('[class*="VbkSUe"], [class*="CNusmb"]')
            ) {
              processCaptionNode(node);
            }
          }
        });
      } else if (mutation.type === 'characterData' && mutation.target.parentElement) {
        processCaptionNode(mutation.target.parentElement);
      }
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  // Check if captions are enabled, if not prompt briefly in console or UI
  console.log('[MeetingMind] Google Meet Caption Observer initialized for meeting:', state.meetingId);
}

// Start observing when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCaptionObserver);
} else {
  initCaptionObserver();
}

export {};
