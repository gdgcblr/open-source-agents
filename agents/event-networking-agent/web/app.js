/**
 * Event Networking World — Minecraft-style block map.
 * Talks to the FastAPI backend (/api/event, /api/world, /api/join, /api/me/room, /api/me/room/meet, /api/me/like, /api/me/connections)
 */

const TILE = 48;
const GRID_W = 24;
const GRID_H = 17;

const ROLE_COLORS = {
  developer: '#38bdf8',
  student: '#a855f7',
  founder: '#f59e0b',
  designer: '#ec4899',
  researcher: '#10b981',
  product: '#6366f1',
  other: '#94a3b8',
};

const ROLE_ICONS = {
  developer: '💻',
  student: '🎓',
  founder: '🚀',
  designer: '🎨',
  researcher: '🔬',
  product: '🧭',
  other: '✨',
};

const SPOT_THEMES = {
  'coffee-corner': { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.13)', icon: '☕', w: 4.4, h: 3.2 },
  'stage-left':    { color: '#ef4444', bg: 'rgba(239, 68, 68, 0.13)',  icon: '🎤', w: 4.8, h: 3.0 },
  'sponsor-alley': { color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.13)', icon: '🎪', w: 4.4, h: 3.4 },
  'hallway-couches': { color: '#a855f7', bg: 'rgba(168, 85, 247, 0.13)', icon: '🛋️', w: 4.4, h: 3.2 },
  'terrace':       { color: '#10b981', bg: 'rgba(16, 185, 129, 0.13)', icon: '🌿', w: 5.0, h: 3.4 },
};

// Pre-computed room pod coordinates in the Networking Concourse that avoid physical spot zones
const ROOM_POD_SLOTS = [
  { x: 9.8,  y: 6.2 },
  { x: 14.0, y: 6.2 },
  { x: 11.8, y: 9.2 },
  { x: 8.2,  y: 13.2 },
  { x: 4.2,  y: 6.6 },
  { x: 18.8, y: 3.6 },
  { x: 19.2, y: 12.6 },
  { x: 15.2, y: 9.4 },
  { x: 7.4,  y: 6.2 },
  { x: 21.5, y: 8.0 },
  { x: 2.5,  y: 10.0 },
  { x: 21.2, y: 13.2 },
];

const SAMPLE_PERSONAS = [
  {
    nickname: 'chai-coder',
    about: 'Backend dev at a payments startup in Bengaluru, mostly Go + Postgres. Hacking on RAG over support tickets and trying Google ADK. Would love to meet folks building AI agents in prod, and open to new roles.',
    contact: '@chai_coder',
  },
  {
    nickname: 'design-dosa',
    about: 'Product designer working on GenAI interfaces and design systems in Figma. Looking to collaborate with frontend devs and agent builders for hackathons.',
    contact: 'dosa.design@example.com',
  },
  {
    nickname: 'kubeflow-kiwi',
    about: 'Founder of an early-stage MLOps & cloud startup. We are hiring backend and ML engineers, and also looking to connect with other founders.',
    contact: '@kiwi_founders',
  },
  {
    nickname: 'neural-namma',
    about: 'Final year CS student in Bengaluru exploring computer vision, LLMs and open-source. Here to learn from mentors and looking for an internship.',
    contact: '@neural_namma',
  },
];

// --- Application State ---
const state = {
  token: localStorage.getItem('ena_token') || null,
  me: null,
  myRoom: null,
  inspectedRoomId: null,
  selectedAttendeeId: null,
  selectedSpotId: null,
  connections: [],
  world: {
    name: 'Road to DevFest 2026 - FORK. BUILD. MERGE.',
    round: 0,
    room_size: 5,
    spots: [],
    attendees: [],
    synthetic_ids: [],
    rooms: [],
    stats: { attendees: 0, round: 0, rooms_this_round: 0, meetups_this_round: 0, mutual_connections: 0, llm: { enabled: false, calls: 0, failures: 0 } },
  },
  avatars: new Map(), // attendee_id -> { x, y, tx, ty, walkPhase, facing, manualTarget, chatText, chatTimer }
  roomPositions: new Map(), // room_id -> { x, y } in tile coords
  camera: {
    x: 0,
    y: 0,
    zoom: 1,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    moved: false,
    follow: true,
  },
  joy: { x: 0, y: 0 },
  keys: new Set(),
  lastPollRound: 0,
  onboardStep: 'form', // form -> working -> ready, then the game takes over
  lastRoomId: null,
};

// --- DOM Elements ---
const canvas = document.getElementById('world-canvas');
const ctx = canvas.getContext('2d');

// --- API Helper ---
async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) {
    headers['X-Attendee-Token'] = state.token;
  }
  const resp = await fetch(path, { ...options, headers });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      msg = err.detail || msg;
    } catch (_) {}
    const error = new Error(msg);
    error.status = resp.status;
    throw error;
  }
  return resp.json();
}

function showToast(message, duration = 3500) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.25s ease';
    setTimeout(() => el.remove(), 250);
  }, duration);
}

function setBanner(text) {
  const banner = document.getElementById('map-banner');
  const bannerText = document.getElementById('map-banner-text');
  if (!text) {
    banner.classList.add('hidden');
  } else {
    bannerText.textContent = text;
    banner.classList.remove('hidden');
  }
}

// --- Deterministic Hash for Avatar Styling & Offsets ---
function hashStr(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// --- Compute Room Pod Positions on Map ---
function computeRoomPositions(rooms) {
  state.roomPositions.clear();
  rooms.forEach((room, idx) => {
    if (idx < ROOM_POD_SLOTS.length) {
      state.roomPositions.set(room.id, ROOM_POD_SLOTS[idx]);
    } else {
      // Fallback grid placement for large events
      const col = idx % 6;
      const row = Math.floor(idx / 6);
      state.roomPositions.set(room.id, {
        x: 3.5 + col * 3.4,
        y: 5.5 + (row % 3) * 3.2,
      });
    }
  });
}

// --- Sync Avatars & Target Waypoints ---
function syncAvatars() {
  const { attendees, rooms, spots, round } = state.world;
  computeRoomPositions(rooms);

  const spotById = new Map(spots.map((s) => [s.id, s]));
  const roomByMember = new Map();
  const memberIndexInRoom = new Map();

  // Track how many rooms are currently booked at each spot so multiple rooms at a big spot don't stack on the exact same pixel
  const roomsAtSpot = new Map();
  rooms.forEach((r) => {
    r.member_ids.forEach((m, idx) => {
      roomByMember.set(m, r);
      memberIndexInRoom.set(m, idx);
    });
    if (r.meetup) {
      const list = roomsAtSpot.get(r.meetup.spot_id) || [];
      list.push(r.id);
      roomsAtSpot.set(r.meetup.spot_id, list);
    }
  });

  const activeIds = new Set(attendees.map((a) => a.id));
  for (const id of state.avatars.keys()) {
    if (!activeIds.has(id)) state.avatars.delete(id);
  }

  // If round changed, clear any manual walking override so everyone walks to their new room!
  const roundChanged = round !== state.lastPollRound;
  if (roundChanged) {
    state.lastPollRound = round;
    for (const av of state.avatars.values()) {
      av.manualTarget = false;
    }
  }

  attendees.forEach((att, idx) => {
    const h = hashStr(att.id);
    let av = state.avatars.get(att.id);

    // Default entrance spawn near bottom-center concourse
    const spawnX = (9.5 + (h % 50) / 10) * TILE;
    const spawnY = (14.8 + ((h >> 8) % 15) / 10) * TILE;

    const spawned = !av;
    if (!av) {
      av = {
        id: att.id,
        x: spawnX,
        y: spawnY,
        tx: spawnX,
        ty: spawnY,
        walkPhase: (h % 100) / 10,
        facing: 1,
        manualTarget: false,
        stateLabel: 'lobby',
        chatText: null,
        chatTimer: 0,
        hadMeetup: false,
      };
      state.avatars.set(att.id, av);
    }

    av.profile = att;
    const room = roomByMember.get(att.id);

    // If the room just booked a meetup, release manualTarget so the user's avatar walks with the group to the physical spot!
    if (room && room.meetup && !av.hadMeetup) {
      av.hadMeetup = true;
      av.manualTarget = false;
    } else if (!room || !room.meetup) {
      av.hadMeetup = false;
    }

    if (av.manualTarget) {
      return;
    }

    if (!room) {
      // Lobby / Concourse milling position
      const angle = ((h % 360) * Math.PI) / 180;
      const radius = 0.6 + ((h >> 4) % 28) / 10;
      const lobbyCenterX = 11.8;
      const lobbyCenterY = 7.8;
      av.tx = (lobbyCenterX + Math.cos(angle) * radius * 1.4) * TILE;
      av.ty = (lobbyCenterY + Math.sin(angle) * radius * 0.9) * TILE;
      av.stateLabel = 'lobby';
    } else if (room.meetup && spotById.has(room.meetup.spot_id)) {
      // Room voted to meet in person -> walk to the Physical Spot Zone!
      const spot = spotById.get(room.meetup.spot_id);
      const spotRooms = roomsAtSpot.get(spot.id) || [room.id];
      const groupIdx = Math.max(0, spotRooms.indexOf(room.id));
      const groupOffsetX = (groupIdx - (spotRooms.length - 1) / 2) * 1.25;

      const mIdx = memberIndexInRoom.get(att.id) || 0;
      const total = Math.max(1, room.member_ids.length);
      const angle = (mIdx / total) * Math.PI * 2 - Math.PI / 2;
      const r = 0.72 * TILE;

      av.tx = (spot.x + groupOffsetX) * TILE + Math.cos(angle) * r;
      av.ty = (spot.y + 0.15) * TILE + Math.sin(angle) * (r * 0.78);
      av.stateLabel = `spot:${spot.name}`;
    } else {
      // Seated at Virtual Room Pod
      const pod = state.roomPositions.get(room.id) || { x: 12, y: 8 };
      const mIdx = memberIndexInRoom.get(att.id) || 0;
      const total = Math.max(1, room.member_ids.length);
      const angle = (mIdx / total) * Math.PI * 2 - Math.PI / 2;
      const seatRadius = 1.15 * TILE;

      av.tx = pod.x * TILE + Math.cos(angle) * seatRadius;
      av.ty = pod.y * TILE + Math.sin(angle) * (seatRadius * 0.85);
      av.stateLabel = `room:${room.id}`;
    }

    if (spawned) {
      av.x = av.tx;
      av.y = av.ty;
    }
  });
}

// --- Poll World & Attendee State ---
async function refreshState() {
  try {
    const world = await api('/api/world');
    state.world = world;

    if (state.token) {
      try {
        const [me, myRoom, connections] = await Promise.all([
          api('/api/me'),
          api('/api/me/room'),
          api('/api/me/connections'),
        ]);
        state.me = me;
        state.myRoom = myRoom;
        state.connections = connections;
      } catch (err) {
        if (err.status === 401) {
          // Server was reset or token expired
          state.token = null;
          state.me = null;
          state.myRoom = null;
          state.connections = [];
          localStorage.removeItem('ena_token');
        }
      }
    }

    syncAvatars();
    renderHUD();
    renderLeftSidebar();
    renderRightSidebar();
    updatePhase();
  } catch (err) {
    console.error('Failed to refresh world state:', err);
  }
}

// --- Render Top HUD ---
function renderHUD() {
  const { name, round, stats } = state.world;
  document.getElementById('event-name').textContent = name;
  document.getElementById('hud-round').textContent = round === 0 ? 'Lobby (Round 0)' : `Round ${round}`;
  document.getElementById('hud-attendees').textContent = stats.attendees;
  document.getElementById('hud-rooms').textContent = stats.rooms_this_round;
  document.getElementById('hud-meetups').textContent = stats.meetups_this_round;
  document.getElementById('hud-connects').textContent = stats.mutual_connections;

  const llmDot = document.getElementById('llm-dot');
  const llmText = document.getElementById('hud-llm');
  if (stats.llm && stats.llm.enabled) {
    llmDot.classList.remove('offline');
    llmText.textContent = `Gemini (${stats.llm.calls} calls)`;
  } else {
    llmDot.classList.add('offline');
    llmText.textContent = 'Offline Fallback';
  }
}

// --- Render Left Sidebar (Join / Me Profile / Spots / Connections) ---
function renderLeftSidebar() {
  const meCard = document.getElementById('me-card');

  if (state.me) {
    meCard.classList.remove('hidden');

    const color = ROLE_COLORS[state.me.role] || ROLE_COLORS.other;
    const dot = document.getElementById('me-avatar-dot');
    dot.style.background = color;
    dot.textContent = ROLE_ICONS[state.me.role] || '✨';

    document.getElementById('me-nickname').textContent = state.me.nickname;
    document.getElementById('me-role').textContent = state.me.role;
    document.getElementById('me-oneliner').textContent = `"${state.me.one_liner}"`;

    const interestsEl = document.getElementById('me-interests');
    interestsEl.innerHTML = '';
    (state.me.interests.length ? state.me.interests : ['general']).forEach((tag) => {
      const span = document.createElement('span');
      span.className = 'tag-chip';
      span.textContent = `#${tag}`;
      interestsEl.appendChild(span);
    });

    const goalsEl = document.getElementById('me-goals');
    goalsEl.innerHTML = '';
    state.me.goals.forEach((g) => {
      const span = document.createElement('span');
      span.className = 'tag-chip goal-chip';
      span.textContent = g;
      goalsEl.appendChild(span);
    });
  } else {
    meCard.classList.add('hidden');
  }

  // Render Physical Spots list with live occupancy
  const spotList = document.getElementById('spot-list');
  spotList.innerHTML = '';
  const spotOccupancy = new Map();
  state.world.rooms.forEach((r) => {
    if (r.meetup) {
      spotOccupancy.set(r.meetup.spot_id, (spotOccupancy.get(r.meetup.spot_id) || 0) + r.member_ids.length);
    }
  });

  state.world.spots.forEach((spot) => {
    const count = spotOccupancy.get(spot.id) || 0;
    const theme = SPOT_THEMES[spot.id] || { icon: '📍', color: '#f59e0b' };
    const div = document.createElement('div');
    div.className = `spot-item ${count > 0 ? 'active-meetup' : ''}`;
    div.innerHTML = `
      <div class="spot-item-top">
        <span>${theme.icon} ${spot.name}</span>
        <span class="spot-cap">${count} / ${spot.capacity} ppl</span>
      </div>
      <div class="spot-desc">${spot.description}</div>
    `;
    div.addEventListener('click', () => {
      state.selectedSpotId = spot.id;
      panToTile(spot.x, spot.y, 1.15);
    });
    spotList.appendChild(div);
  });

  // Render Mutual Connections
  const connCount = document.getElementById('connections-count');
  const connList = document.getElementById('connections-list');
  connCount.textContent = state.connections.length;
  // Badge the dock button so new contacts are findable while the panel is closed.
  const dockCount = document.getElementById('dock-connections');
  dockCount.textContent = state.connections.length;
  dockCount.classList.toggle('hidden', !state.connections.length);

  if (!state.connections.length) {
    connList.innerHTML = `<div class="empty-hint">No mutual connections yet. Click "Stay in touch" on roommates you vibe with!</div>`;
  } else {
    connList.innerHTML = '';
    state.connections.forEach((c) => {
      const item = document.createElement('div');
      item.className = 'connection-item';
      item.innerHTML = `
        <span class="connection-nick">🤝 ${escapeHtml(c.nickname)}</span>
        <span class="connection-contact">${escapeHtml(c.contact || 'No contact shared')}</span>
      `;
      connList.appendChild(item);
    });
  }
}

// --- Render Right Sidebar (Room Card, Icebreaker, Meet in Person, Roommates) ---
function renderRightSidebar() {
  const noRoomCard = document.getElementById('no-room-card');
  const roomCard = document.getElementById('room-card');

  // Determine which room to show: user's inspected room on the floor, or their own assigned room, or the first room if spectator
  let activeRoom = null;
  let isMyRoom = false;

  if (state.inspectedRoomId) {
    const found = state.world.rooms.find((r) => r.id === state.inspectedRoomId);
    if (found) {
      if (state.myRoom && found.id === state.myRoom.id) {
        activeRoom = state.myRoom;
        isMyRoom = true;
      } else {
        activeRoom = hydrateFloorRoom(found);
        isMyRoom = false;
      }
    } else {
      state.inspectedRoomId = null;
    }
  }

  if (!activeRoom && state.myRoom) {
    activeRoom = state.myRoom;
    isMyRoom = true;
  } else if (!activeRoom && state.world.rooms.length > 0) {
    activeRoom = hydrateFloorRoom(state.world.rooms[0]);
    isMyRoom = false;
  }

  if (!activeRoom) {
    noRoomCard.classList.remove('hidden');
    roomCard.classList.add('hidden');
    const msgEl = document.getElementById('no-room-message');
    if (state.world.attendees.length === 0) {
      msgEl.innerHTML = `Click <strong>⚡ Quick Demo Setup</strong> below to populate the venue floor and start Round 1!`;
    } else if (state.world.round === 0) {
      msgEl.innerHTML = `<strong>${state.world.attendees.length} attendees</strong> are mingling in the Lobby! Tap <strong>▶ Start next round</strong> (Tools menu on mobile) to group everyone into rooms.`;
    }
    return;
  }

  noRoomCard.classList.add('hidden');
  roomCard.classList.remove('hidden');

  const ownerBadge = document.getElementById('room-badge-owner');
  const backBtn = document.getElementById('btn-back-my-room');

  if (isMyRoom) {
    ownerBadge.textContent = 'YOUR ROOM';
    ownerBadge.className = 'badge badge-cyan';
    backBtn.classList.add('hidden');
  } else {
    ownerBadge.textContent = state.myRoom ? 'INSPECTING FLOOR ROOM' : 'SPECTATOR VIEW';
    ownerBadge.className = 'badge badge-amber';
    if (state.myRoom) {
      backBtn.classList.remove('hidden');
    } else {
      backBtn.classList.add('hidden');
    }
  }

  document.getElementById('room-round-label').textContent = `Round ${activeRoom.round}`;
  document.getElementById('room-title').textContent = `Room ${activeRoom.id}`;

  // Shared interests
  const sharedContainer = document.getElementById('room-shared-interests');
  sharedContainer.innerHTML = '';
  (activeRoom.shared_interests || []).forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.textContent = `#${tag}`;
    sharedContainer.appendChild(chip);
  });

  // Why & Icebreaker
  document.getElementById('room-why').textContent = activeRoom.why;
  document.getElementById('room-icebreaker').textContent = `"${activeRoom.icebreaker}"`;

  // Votes & Meet in Person
  const votes = activeRoom.votes;
  const needed = activeRoom.votes_needed;
  const pct = Math.min(100, Math.round((votes / Math.max(1, needed)) * 100));
  document.getElementById('room-vote-counter').textContent = `${votes} / ${needed} votes needed`;
  document.getElementById('room-vote-fill').style.width = `${pct}%`;

  const voteBtn = document.getElementById('btn-vote-meet');
  const voteHint = document.getElementById('room-vote-hint');
  const ticket = document.getElementById('meetup-ticket');

  if (isMyRoom) {
    voteBtn.classList.remove('hidden');
    if (activeRoom.i_voted) {
      voteBtn.className = 'btn btn-meet voted btn-block';
      voteBtn.textContent = activeRoom.meetup
        ? '✓ You Voted — Meetup Spot Booked!'
        : `✓ You Voted (${votes}/${needed}) — Click "⚡ Simulate Votes" in top bar for bots`;
      voteBtn.disabled = true;
    } else {
      voteBtn.className = 'btn btn-meet btn-block';
      voteBtn.textContent = '🤝 Meet in Person (Cast Vote)';
      voteBtn.disabled = false;
    }
  } else {
    voteBtn.classList.add('hidden');
  }

  if (activeRoom.meetup) {
    ticket.classList.remove('hidden');
    voteHint.classList.add('hidden');
    const m = activeRoom.meetup;
    document.getElementById('meetup-spot-name').textContent = m.spot_name;
    document.getElementById('meetup-spot-desc').textContent = m.spot_description;
    document.getElementById('meetup-time').textContent = `${formatTime(m.meet_at)} – ${formatTime(m.until)}`;
    const focusBtn = document.getElementById('btn-focus-spot');
    focusBtn.onclick = () => {
      const spot = state.world.spots.find((s) => s.id === m.spot_id);
      if (spot) panToTile(spot.x, spot.y, 1.2);
    };
  } else {
    ticket.classList.add('hidden');
    voteHint.classList.remove('hidden');
  }

  // Room Members list
  const membersList = document.getElementById('room-members-list');
  membersList.innerHTML = '';
  const likedSet = new Set(activeRoom.liked_ids || []);
  const mutualSet = new Set(activeRoom.mutual_ids || []);

  activeRoom.members.forEach((m) => {
    const isSelf = state.me && m.id === state.me.id;
    const color = ROLE_COLORS[m.role] || ROLE_COLORS.other;
    const icon = ROLE_ICONS[m.role] || '✨';

    const card = document.createElement('div');
    card.className = `member-item ${isSelf ? 'is-me' : ''}`;

    let actionHtml = '';
    if (isSelf) {
      actionHtml = `<span class="badge badge-amber">YOU</span>`;
    } else if (isMyRoom && state.me) {
      if (mutualSet.has(m.id)) {
        actionHtml = `<button class="btn-like mutual" disabled>✨ Connected</button>`;
      } else if (likedSet.has(m.id)) {
        actionHtml = `<button class="btn-like liked" disabled>👋 Liked (Waiting)</button>`;
      } else {
        actionHtml = `<button class="btn-like" data-like-id="${m.id}">👋 Stay in touch</button>`;
      }
    }

    const tagsHtml = [
      ...m.interests.map((t) => `<span class="tag-chip">#${escapeHtml(t)}</span>`),
      ...m.goals.map((g) => `<span class="tag-chip goal-chip">${escapeHtml(g)}</span>`),
    ].join('');

    card.innerHTML = `
      <div class="member-top">
        <div class="member-ident">
          <div class="member-dot" style="background:${color}">${icon}</div>
          <div>
            <div class="member-name">${escapeHtml(m.nickname)}</div>
            <span class="role-badge">${escapeHtml(m.role)}</span>
          </div>
        </div>
        ${actionHtml}
      </div>
      <div class="member-oneliner">${escapeHtml(m.one_liner)}</div>
      <div class="member-tags">${tagsHtml}</div>
    `;

    card.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      const av = state.avatars.get(m.id);
      if (av) {
        state.selectedAttendeeId = m.id;
        panToPixel(av.x, av.y, 1.2);
      }
    });

    const likeBtn = card.querySelector('[data-like-id]');
    if (likeBtn) {
      likeBtn.addEventListener('click', async () => {
        likeBtn.disabled = true;
        try {
          const res = await api('/api/me/like', {
            method: 'POST',
            body: JSON.stringify({ to_id: m.id }),
          });
          if (res.mutual) {
            showToast(`🎉 Mutual connection with ${m.nickname}! Contact unlocked under You & places.`);
            // Desktop fits both panels; on phones keep the Room sheet up and let the dock badge point the way.
            if (!isMobile()) openPanel('panel-left');
          } else {
            showToast(`👋 Sent "Stay in touch" to ${m.nickname}.`);
          }
          await refreshState();
        } catch (err) {
          showToast(`Error: ${err.message}`);
          likeBtn.disabled = false;
        }
      });
    }

    membersList.appendChild(card);
  });
}

function hydrateFloorRoom(floorRoom) {
  const byId = new Map(state.world.attendees.map((a) => [a.id, a]));
  return {
    ...floorRoom,
    members: floorRoom.member_ids.map((id) => byId.get(id)).filter(Boolean),
    i_voted: false,
    liked_ids: [],
    mutual_ids: [],
  };
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) {
    return '';
  }
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// --- Camera & Canvas Helpers ---
function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function fitVenueCamera() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const mapW = GRID_W * TILE;
  const mapH = GRID_H * TILE;
  const scaleX = (rect.width - 40) / mapW;
  const scaleY = (rect.height - 40) / mapH;
  state.camera.zoom = Math.max(0.55, Math.min(1.25, Math.min(scaleX, scaleY)));
  if (state.me && document.body.dataset.phase === 'play') state.camera.zoom = Math.max(state.camera.zoom, isMobile() ? 0.9 : 1);
  state.camera.x = (rect.width - mapW * state.camera.zoom) / 2;
  state.camera.y = (rect.height - mapH * state.camera.zoom) / 2;
}

function panToTile(tx, ty, zoom = null) {
  panToPixel(tx * TILE, ty * TILE, zoom);
}

function panToPixel(px, py, zoom = null) {
  const rect = canvas.parentElement.getBoundingClientRect();
  if (zoom !== null) state.camera.zoom = zoom;
  state.camera.x = rect.width / 2 - px * state.camera.zoom;
  state.camera.y = rect.height / 2 - py * state.camera.zoom;
}

function screenToWorld(sx, sy) {
  return {
    x: (sx - state.camera.x) / state.camera.zoom,
    y: (sy - state.camera.y) / state.camera.zoom,
  };
}

// --- 2D Map Drawing Engine (60fps loop) ---
let lastFrameTime = performance.now();

function updateCamera(dt) {
  const rect = canvas.parentElement.getBoundingClientRect();
  const cam = state.camera;
  const me = state.me && state.avatars.get(state.me.id);
  if (cam.follow && !cam.dragging && me && document.body.dataset.phase === 'play') {
    const k = 1 - Math.exp(-6 * dt); // frame-rate independent smoothing
    cam.x += (rect.width / 2 - me.x * cam.zoom - cam.x) * k;
    cam.y += (rect.height / 2 - (me.y - 16) * cam.zoom - cam.y) * k;
  }
  // Keep the view inside the woodland margin; if the whole venue fits, centre it.
  const m = 3 * TILE;
  const worldW = (GRID_W * TILE + m * 2) * cam.zoom;
  const worldH = (GRID_H * TILE + m * 2) * cam.zoom;
  const minX = rect.width - (GRID_W * TILE + m) * cam.zoom;
  const minY = rect.height - (GRID_H * TILE + m) * cam.zoom;
  cam.x = worldW <= rect.width ? (rect.width - GRID_W * TILE * cam.zoom) / 2 : Math.min(m * cam.zoom, Math.max(minX, cam.x));
  cam.y = worldH <= rect.height ? (rect.height - GRID_H * TILE * cam.zoom) / 2 : Math.min(m * cam.zoom, Math.max(minY, cam.y));
}

function tickAndDraw(now) {
  const dt = Math.min(0.05, (now - lastFrameTime) / 1000);
  lastFrameTime = now;

  updateAvatarPhysics(dt);
  updateCamera(dt);
  updateInteractHint(now);
  drawWorld(now);

  requestAnimationFrame(tickAndDraw);
}

function solidAt(px, py) {
  ensureTerrain();
  const tx = Math.floor(px / TILE);
  const ty = Math.floor(py / TILE);
  if (terrain[ty] && terrain[ty][tx] === 'water') return true;
  return solidTrees.some((t) => Math.hypot(px - t.x, py - t.y) < 15);
}

function updateAvatarPhysics(dt) {
  // WASD / arrows / on-screen joystick move the local avatar, with collision.
  if (state.me && state.avatars.has(state.me.id)) {
    const myAv = state.avatars.get(state.me.id);
    let dx = 0;
    let dy = 0;
    if (state.keys.has('ArrowUp') || state.keys.has('KeyW')) dy -= 1;
    if (state.keys.has('ArrowDown') || state.keys.has('KeyS')) dy += 1;
    if (state.keys.has('ArrowLeft') || state.keys.has('KeyA')) dx -= 1;
    if (state.keys.has('ArrowRight') || state.keys.has('KeyD')) dx += 1;
    let power = 1;
    if (dx === 0 && dy === 0 && Math.hypot(state.joy.x, state.joy.y) > 0.15) {
      dx = state.joy.x;
      dy = state.joy.y;
      power = Math.min(1, Math.hypot(dx, dy));
    }
    if (dx !== 0 || dy !== 0) {
      const len = Math.hypot(dx, dy);
      const step = 210 * power * dt;
      const nx = Math.max(TILE, Math.min((GRID_W - 1) * TILE, myAv.x + (dx / len) * step));
      const ny = Math.max(TILE, Math.min((GRID_H - 1) * TILE, myAv.y + (dy / len) * step));
      if (!solidAt(nx, myAv.y)) myAv.x = nx; // axis-separated so you slide along obstacles
      if (!solidAt(myAv.x, ny)) myAv.y = ny;
      myAv.manualTarget = true;
      myAv.tx = myAv.x;
      myAv.ty = myAv.y;
      state.camera.follow = true;
      if (Math.abs(dx) > 0.1) myAv.facing = dx > 0 ? 1 : -1;
      myAv.walkPhase += dt * 12;
      myAv.isWalking = true;
    }
  }

  const chatPhrases = [
    'Great icebreaker!',
    'Let’s build!',
    'Anyone into ADK?',
    'Let’s stay in touch 👋',
    'Love this spot!',
    'Shipping agents 🚀',
    'Coffee time ☕',
  ];

  for (const av of state.avatars.values()) {
    const dx = av.tx - av.x;
    const dy = av.ty - av.y;
    const dist = Math.hypot(dx, dy);

    if (dist > 2.0) {
      const speed = Math.min(200, Math.max(85, dist * 2.1));
      const step = Math.min(dist, speed * dt);
      av.x += (dx / dist) * step;
      av.y += (dy / dist) * step;
      if (Math.abs(dx) > 0.5) av.facing = dx > 0 ? 1 : -1;
      av.walkPhase += dt * 11;
      av.isWalking = true;
    } else {
      av.x = av.tx;
      av.y = av.ty;
      av.isWalking = false;
      av.walkPhase += dt * 1.8;

      // Occasional ambient chat bubble when gathered in a room or spot
      if (av.stateLabel !== 'lobby') {
        av.chatTimer -= dt;
        if (av.chatTimer <= -4 && Math.random() < 0.004) {
          const interests = av.profile?.interests || [];
          av.chatText = interests.length && Math.random() < 0.5
            ? `#${interests[0]}!`
            : chatPhrases[hashStr(av.id + Math.floor(lastFrameTime / 3000)) % chatPhrases.length];
          av.chatTimer = 2.8;
        }
      }
    }
    if (av.chatTimer > 0) {
      av.chatTimer -= dt;
      if (av.chatTimer <= 0) av.chatText = null;
    }
  }
}

function drawWorld(now) {
  const rect = canvas.parentElement.getBoundingClientRect();
  ctx.fillStyle = '#4e8c32';
  ctx.fillRect(0, 0, rect.width, rect.height);

  ctx.save();
  ctx.translate(state.camera.x, state.camera.y);
  ctx.scale(state.camera.zoom, state.camera.zoom);

  const vis = visibleTiles(rect);
  drawTerrain(now, vis);
  drawTrees(vis);
  drawPlazaProps(now);
  drawPhysicalSpots(now);
  drawVirtualRoomPods(now);
  drawMeetupPaths(now);
  drawAvatars(now);

  ctx.restore();
}

const REDUCE_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const SKINS = ['#f6d7b0', '#e0ac69', '#c68642', '#a56b45', '#8d5524'];
const HAIR = ['#2a1a10', '#1a1a1a', '#6b4423', '#d4a017', '#3d2b1f'];
const WOOL = ['#c44141', '#e39b2b', '#f2d04b', '#3f8f34', '#3a74e0', '#8a4fbf', '#e07ab0'];
const TREE_CANDIDATES = [
  [2, 3], [3, 5], [8, 2], [8, 4], [9, 5], [16, 3], [17, 5], [22, 2], [22, 5],
  [2, 6], [1, 9], [3, 11], [5, 14], [7, 15], [9, 12], [10, 15], [11, 11],
  [16, 11], [19, 15], [20, 5], [21, 11], [22, 13],
];
const YARD_SHORT = {
  'coffee-corner': 'COFFEE',
  'stage-left': 'STAGE',
  'sponsor-alley': 'BOOTHS',
  'hallway-couches': 'COUCHES',
  'terrace': 'TERRACE',
};

let solidTrees = [];
let terrain = null;
let terrainKey = '';

// Cheap integer hash for per-tile variation (drawTile runs for every visible tile each frame).
function ihash(x, y) {
  let h = (Math.imul(x, 374761393) + Math.imul(y, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return (h ^ (h >>> 16)) >>> 0;
}

function isPond(x, y) {
  return x >= 20 && x <= 22 && y >= 14 && y <= 15;
}

function onPath(x, y, spots) {
  if (Math.abs(x - 12) <= 2 && Math.abs(y - 8) <= 1) return true;
  if (y === 8 && x >= 1 && x <= GRID_W - 2) return true;
  for (const spot of spots) {
    if (spot.x == null || spot.y == null) continue;
    const sx = Math.round(spot.x);
    const y0 = Math.min(Math.round(spot.y), 8);
    const y1 = Math.max(Math.round(spot.y), 8);
    if (x === sx && y >= y0 && y <= y1) return true;
  }
  return false;
}

function nearPond(x, y) {
  return [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => isPond(x + dx, y + dy));
}

function ensureTerrain() {
  const spots = state.world.spots || [];
  const key = spots.map((s) => `${s.id}:${s.x}:${s.y}`).join('|');
  if (terrain && key === terrainKey) return;
  terrainKey = key;
  terrain = [];
  for (let y = 0; y < GRID_H; y++) {
    const row = [];
    for (let x = 0; x < GRID_W; x++) {
      let kind = 'grass';
      if (isPond(x, y)) kind = 'water';
      else if (onPath(x, y, spots)) kind = 'cobble';
      else if (nearPond(x, y)) kind = 'sand';
      row.push(kind);
    }
    terrain.push(row);
  }
  solidTrees = TREE_CANDIDATES
    .filter(([x, y]) => x > 0 && y > 0 && x < GRID_W - 1 && y < GRID_H - 1 && !tileBlocked(x, y))
    .map(([x, y]) => ({ x: x * TILE + TILE / 2, y: y * TILE + TILE / 2 + 8 }));
}

function visibleTiles(rect) {
  const z = state.camera.zoom;
  return {
    x0: Math.floor(-state.camera.x / z / TILE) - 1,
    y0: Math.floor(-state.camera.y / z / TILE) - 1,
    x1: Math.ceil((rect.width - state.camera.x) / z / TILE) + 1,
    y1: Math.ceil((rect.height - state.camera.y) / z / TILE) + 1,
  };
}

// The venue is finite, but the meadow is drawn to every edge of the viewport so no frame or
// void is ever visible. Outside the playable area it is woodland; the tree line is the limit.
function drawTerrain(now, vis) {
  ensureTerrain();
  for (let y = vis.y0; y <= vis.y1; y++) {
    for (let x = vis.x0; x <= vis.x1; x++) {
      const inside = x >= 0 && y >= 0 && x < GRID_W && y < GRID_H;
      drawTile(x, y, inside ? terrain[y][x] : 'grass', now);
    }
  }
}

function drawTile(x, y, kind, now) {
  const px = x * TILE;
  const py = y * TILE;
  const h = ihash(x, y);
  if (kind === 'grass') {
    const greens = ['#5a9a38', '#549434', '#62a340', '#4e8c32'];
    ctx.fillStyle = greens[h % greens.length];
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#3e7424';
    ctx.fillRect(px + (h % (TILE - 6)), py + ((h >> 4) % (TILE - 6)), 2, 4);
    ctx.fillStyle = '#7cbc4a';
    ctx.fillRect(px + ((h >> 8) % (TILE - 6)), py + ((h >> 12) % (TILE - 6)), 2, 2);
    if (h % 13 === 0) {
      ctx.fillStyle = h % 2 ? '#e23b3b' : '#f2d04b';
      ctx.fillRect(px + 18, py + 16, 4, 4);
      ctx.fillStyle = '#2f6a22';
      ctx.fillRect(px + 19, py + 20, 2, 5);
    }
    return;
  }
  if (kind === 'cobble') {
    ctx.fillStyle = '#8d8d8d';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#6f6f6f';
    ctx.fillRect(px + (h % 22), py + ((h >> 3) % 22), 10, 7);
    ctx.fillStyle = '#b0b0b0';
    ctx.fillRect(px + ((h >> 6) % 26), py + ((h >> 9) % 26), 6, 5);
    return;
  }
  if (kind === 'water') {
    const shift = REDUCE_MOTION ? 0 : Math.floor(now / 420) % 2;
    ctx.fillStyle = shift ? '#2e66d0' : '#3a74e0';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.fillRect(px + 8 + shift * 6, py + 10, 14, 3);
    ctx.fillRect(px + 22 - shift * 4, py + 26, 10, 3);
    return;
  }
  if (kind === 'sand') {
    ctx.fillStyle = h % 2 ? '#e6d39a' : '#d8c48a';
    ctx.fillRect(px, py, TILE, TILE);
    ctx.fillStyle = '#cbb67a';
    ctx.fillRect(px + (h % 30), py + ((h >> 5) % 30), 3, 3);
    return;
  }
  ctx.fillStyle = (x + y) % 2 ? '#7a7a7a' : '#686868';
  ctx.fillRect(px, py, TILE, TILE);
  ctx.fillStyle = '#9a9a9a';
  ctx.fillRect(px, py, TILE, 3);
  ctx.fillStyle = '#505050';
  ctx.fillRect(px, py + TILE - 3, TILE, 3);
}

function tileBlocked(x, y) {
  if (!terrain || terrain[y][x] !== 'grass') return true;
  for (const spot of state.world.spots || []) {
    const theme = SPOT_THEMES[spot.id] || { w: 4.2, h: 3.0 };
    if (Math.abs(x - spot.x) < theme.w / 2 + 0.4 && Math.abs(y - spot.y) < theme.h / 2 + 0.4) return true;
  }
  for (const slot of ROOM_POD_SLOTS) {
    if (Math.hypot(x - slot.x, y - slot.y) < 1.7) return true;
  }
  return false;
}

function drawTrees(vis) {
  ensureTerrain();
  const ring = (x, y) => x <= 0 || y <= 0 || x >= GRID_W - 1 || y >= GRID_H - 1;
  for (let y = vis.y0; y <= vis.y1; y++) {
    for (let x = vis.x0; x <= vis.x1; x++) {
      if (x > 0 && y > 0 && x < GRID_W - 1 && y < GRID_H - 1) continue; // interior handled below
      // Distance outside the playable area: dense at the edge, thinning to scattered woodland.
      const d = Math.max(-x, x - (GRID_W - 1), -y, y - (GRID_H - 1), 0);
      const h = ihash(x + 977, y + 313);
      const dense = ring(x, y) && d === 0 ? true : (h % 100) < (d <= 2 ? 78 : 42);
      if (!dense) continue;
      drawTree(x * TILE + TILE / 2 + ((h >> 8) % 13) - 6, y * TILE + TILE / 2 + ((h >> 12) % 11) - 5);
    }
  }
  solidTrees.forEach((t) => drawTree(t.x, t.y - 8));
}

function drawTree(cx, cy) {
  ctx.fillStyle = '#246422';
  ctx.fillRect(cx - 16, cy - 20, 32, 24);
  ctx.fillStyle = '#3e9434';
  ctx.fillRect(cx - 10, cy - 28, 20, 16);
  ctx.fillStyle = '#2f7a28';
  ctx.fillRect(cx - 20, cy - 12, 12, 14);
  ctx.fillRect(cx + 8, cy - 14, 12, 12);
  ctx.fillStyle = '#6b4a28';
  ctx.fillRect(cx - 3, cy + 2, 6, 14);
  ctx.fillStyle = '#4e331c';
  ctx.fillRect(cx - 4, cy + 14, 8, 3);
}

function glow(x, y, r, color, alpha) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, color.replace('A', alpha));
  g.addColorStop(1, color.replace('A', 0));
  ctx.fillStyle = g;
  ctx.fillRect(x - r, y - r, r * 2, r * 2);
}

function drawPlazaProps(now) {
  const cx = 12 * TILE + TILE / 2;
  const cy = 8 * TILE + TILE / 2;
  const t = REDUCE_MOTION ? 0 : now / 1000;

  // Stone ring + logs
  ctx.fillStyle = '#5a5a5a';
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    ctx.fillRect(cx + Math.cos(a) * 20 - 4, cy + Math.sin(a) * 15 - 3, 8, 6);
  }
  ctx.fillStyle = '#6b4423';
  ctx.fillRect(cx - 14, cy + 2, 28, 5);
  ctx.fillRect(cx - 5, cy - 3, 10, 14);
  ctx.fillStyle = '#4e331c';
  ctx.fillRect(cx - 14, cy + 5, 28, 2);

  // Flames flicker on a few offset sine waves
  const f1 = 14 + Math.sin(t * 9) * 3, f2 = 10 + Math.sin(t * 12 + 1) * 3, f3 = 7 + Math.sin(t * 15 + 2) * 2;
  ctx.fillStyle = '#e8501c'; ctx.fillRect(cx - 8, cy - f1, 16, f1 + 2);
  ctx.fillStyle = '#f59e0b'; ctx.fillRect(cx - 5, cy - f2 - 2, 10, f2 + 2);
  ctx.fillStyle = '#fde68a'; ctx.fillRect(cx - 2, cy - f3, 4, f3);

  // Warm glow + a bounded handful of rising sparks
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  glow(cx, cy - 4, 130 + Math.sin(t * 7) * 6, 'rgba(255,150,40,A)', 0.32);
  ctx.restore();
  if (!REDUCE_MOTION) {
    for (let i = 0; i < 6; i++) {
      const life = (t * 0.7 + i / 6) % 1;
      ctx.fillStyle = `rgba(253,224,138,${1 - life})`;
      ctx.fillRect(cx - 10 + ((i * 37) % 21) + Math.sin(t * 3 + i) * 5, cy - 14 - life * 40, 3, 3);
    }
  }

  [3, 7, 16, 20].forEach((tx) => {
    const lx = tx * TILE + TILE / 2;
    const ly = 8 * TILE;
    ctx.fillStyle = '#5a3a22';
    ctx.fillRect(lx - 2, ly - 18, 4, 20);
    ctx.fillStyle = '#f6e27a';
    ctx.fillRect(lx - 4, ly - 24, 8, 6);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    glow(lx, ly - 21, 46, 'rgba(255,214,110,A)', 0.22);
    ctx.restore();
  });
}

function spotBox(spot) {
  const theme = SPOT_THEMES[spot.id] || { w: 4.2, h: 3.0 };
  const zw = theme.w * TILE;
  const zh = theme.h * TILE;
  return { zx: spot.x * TILE - zw / 2, zy: spot.y * TILE - zh / 2, zw, zh };
}

function fillPlanks(x, y, w, h) {
  ctx.fillStyle = '#c6a15a';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = '#a8843e';
  for (let py = y; py < y + h; py += 8) ctx.fillRect(x, py, w, 1);
  ctx.fillStyle = 'rgba(90,58,34,0.35)';
  for (let px = x + 10; px < x + w; px += 18) ctx.fillRect(px, y, 1, h);
}

function fillCobbleRect(x, y, w, h) {
  ctx.fillStyle = '#8d8d8d';
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = '#6f6f6f';
  for (let i = 0; i < 8; i++) {
    ctx.fillRect(x + ((i * 37) % Math.max(8, w - 10)), y + ((i * 19) % Math.max(8, h - 8)), 8, 5);
  }
}

function drawShelter(box, doorSouth) {
  const { zx, zy, zw, zh } = box;
  const depth = Math.min(22, zh * 0.28);
  ctx.fillStyle = '#8d5a32';
  if (doorSouth) ctx.fillRect(zx, zy, zw, depth);
  else ctx.fillRect(zx, zy + zh - depth, zw, depth);
  ctx.fillStyle = '#5a3a22';
  if (doorSouth) ctx.fillRect(zx, zy + depth - 4, zw, 4);
  else ctx.fillRect(zx, zy + zh - depth, zw, 4);
  ctx.fillStyle = '#4e331c';
  ctx.fillRect(zx, zy, 5, doorSouth ? zh * 0.62 : zh);
  ctx.fillRect(zx + zw - 5, zy, 5, doorSouth ? zh * 0.62 : zh);
}

function drawPostFence(x, y, w, h) {
  ctx.fillStyle = '#6b4423';
  const step = 18;
  for (let px = x; px <= x + w - 4; px += step) {
    ctx.fillRect(px, y, 4, 7);
    ctx.fillRect(px, y + h - 7, 4, 7);
  }
  for (let py = y; py <= y + h - 4; py += step) {
    ctx.fillRect(x, py, 4, 7);
    ctx.fillRect(x + w - 4, py, 4, 7);
  }
  ctx.fillStyle = '#8a6239';
  ctx.fillRect(x, y + 2, w, 2);
  ctx.fillRect(x, y + h - 4, w, 2);
  ctx.fillRect(x, y, 2, h);
  ctx.fillRect(x + w - 2, y, 2, h);
}

function drawFence(x, y, w, h, doorOnSouth) {
  const t = 5;
  const gap = Math.min(34, w * 0.32);
  const gapX = x + (w - gap) / 2;
  const beam = (bx, by, bw, bh) => {
    if (bw <= 0 || bh <= 0) return;
    ctx.fillStyle = '#7a5230';
    ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = '#4e331c';
    ctx.fillRect(bx, by + bh - 2, bw, 2);
  };
  if (doorOnSouth) beam(x, y, w, t);
  else {
    beam(x, y, gapX - x, t);
    beam(gapX + gap, y, x + w - (gapX + gap), t);
  }
  if (!doorOnSouth) beam(x, y + h - t, w, t);
  else {
    beam(x, y + h - t, gapX - x, t);
    beam(gapX + gap, y + h - t, x + w - (gapX + gap), t);
  }
  beam(x, y, t, h);
  beam(x + w - t, y, t, h);
  ctx.fillStyle = '#3e2916';
  [[x, y], [x + w - t, y], [x, y + h - t], [x + w - t, y + h - t]].forEach(([px, py]) => {
    ctx.fillRect(px - 1, py - 1, t + 2, t + 2);
  });
}

function drawSign(x, y, text) {
  ctx.font = '700 8px "Press Start 2P", ui-monospace, monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const w = Math.min(168, Math.max(46, ctx.measureText(text).width + 14));
  ctx.fillStyle = '#5a3a22';
  ctx.fillRect(x - 2, y, 4, 14);
  ctx.fillStyle = '#c4a46a';
  ctx.fillRect(x - w / 2, y - 16, w, 16);
  ctx.fillStyle = '#8a6a32';
  ctx.fillRect(x - w / 2, y - 16, w, 3);
  ctx.fillStyle = '#3a2a14';
  ctx.fillText(text, x, y - 8);
}

function drawPhysicalSpots() {
  const occupied = new Map();
  state.world.rooms.forEach((room) => {
    if (!room.meetup) return;
    occupied.set(room.meetup.spot_id, (occupied.get(room.meetup.spot_id) || 0) + room.member_ids.length);
  });
  state.world.spots.forEach((spot) => {
    if (spot.x == null || spot.y == null) return;
    const box = spotBox(spot);
    const doorSouth = spot.y <= 8;
    const count = occupied.get(spot.id) || 0;
    if (spot.id === 'terrace') {
      /* garden keeps the grass */
    } else if (spot.id === 'sponsor-alley') {
      fillCobbleRect(box.zx, box.zy, box.zw, box.zh);
    } else {
      fillPlanks(box.zx, box.zy, box.zw, box.zh);
    }
    drawYardFurniture(spot.id, box);
    if (spot.id === 'stage-left') drawStageBackdrop(box);
    else if (spot.id === 'terrace') drawPostFence(box.zx, box.zy, box.zw, box.zh);
    else drawShelter(box, doorSouth);
    const short = YARD_SHORT[spot.id] || 'SPOT';
    drawSign(box.zx + box.zw / 2, box.zy + 20, count ? `${short} ${count}` : short);
  });
}

function drawYardFurniture(id, box) {
  const { zx, zy, zw, zh } = box;
  if (id === 'coffee-corner') {
    ctx.fillStyle = '#5a3a22';
    ctx.fillRect(zx + 12, zy + 28, zw - 24, 14);
    ctx.fillStyle = '#f4f4f4';
    ctx.fillRect(zx + 28, zy + 31, 6, 5);
    ctx.fillRect(zx + 48, zy + 31, 6, 5);
    ctx.fillStyle = '#c44141';
    ctx.fillRect(zx + zw - 36, zy + zh - 36, 14, 10);
    ctx.fillStyle = '#f4f4f4';
    ctx.fillRect(zx + zw - 36, zy + zh - 40, 14, 4);
  } else if (id === 'sponsor-alley') {
    const colors = ['#c44141', '#3a74e0', '#f2d04b'];
    colors.forEach((color, i) => {
      const ax = zx + 16 + i * ((zw - 40) / 3);
      ctx.fillStyle = color;
      ctx.fillRect(ax, zy + 26, 36, 8);
      ctx.fillStyle = '#6b4423';
      ctx.fillRect(ax + 4, zy + 34, 28, 16);
    });
  } else if (id === 'hallway-couches') {
    ctx.fillStyle = '#9b2c2c';
    ctx.fillRect(zx + 16, zy + 36, 52, 16);
    ctx.fillStyle = '#1d4e89';
    ctx.fillRect(zx + 16, zy + 36, 14, 40);
    ctx.fillStyle = '#d8d8d8';
    ctx.fillRect(zx + zw - 48, zy + zh / 2, 22, 16);
  } else if (id === 'terrace') {
    ctx.fillStyle = '#c4a84a';
    ctx.fillRect(zx + 14, zy + 18, 16, 12);
    ctx.fillStyle = '#3e9434';
    ctx.fillRect(zx + zw - 32, zy + 16, 16, 14);
    ctx.fillStyle = '#e23b3b';
    ctx.fillRect(zx + 22, zy + zh - 28, 4, 4);
    ctx.fillStyle = '#f2d04b';
    ctx.fillRect(zx + 34, zy + zh - 24, 4, 4);
    ctx.fillStyle = '#3a74e0';
    ctx.fillRect(zx + zw / 2 - 8, zy + zh / 2, 16, 12);
  }
}

function drawStageBackdrop(box) {
  const { zx, zy, zw } = box;
  ctx.fillStyle = '#9b2c2c';
  ctx.fillRect(zx, zy, zw, 18);
  ctx.fillStyle = '#f2d04b';
  ctx.fillRect(zx + 8, zy + 5, zw - 16, 4);
  ctx.fillStyle = '#5c3a1e';
  ctx.fillRect(zx + 18, zy + 28, 14, 14);
  ctx.fillRect(zx + zw - 32, zy + 28, 14, 14);
}

function drawMeetupPaths(now) {
  const room = state.myRoom
    || state.world.rooms.find((r) => r.id === state.inspectedRoomId);
  if (!room || !room.meetup) return;
  const pod = state.roomPositions.get(room.id);
  const spot = state.world.spots.find((s) => s.id === room.meetup.spot_id);
  if (!pod || !spot || spot.x == null) return;
  const x1 = pod.x * TILE;
  const y1 = pod.y * TILE;
  const x2 = spot.x * TILE;
  const y2 = spot.y * TILE;
  const steps = 14;
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const bob = REDUCE_MOTION ? 0 : Math.sin(now / 180 + i) * 3;
    const x = x1 + (x2 - x1) * t;
    const y = y1 + (y2 - y1) * t + bob;
    ctx.fillStyle = i % 2 ? '#3ddc6a' : '#ffe56a';
    ctx.fillRect(x - 2, y - 2, 4, 4);
  }
}

function drawVirtualRoomPods(now) {
  state.world.rooms.forEach((room, index) => {
    const pod = state.roomPositions.get(room.id);
    if (!pod) return;
    const cx = pod.x * TILE;
    const cy = pod.y * TILE;
    const mine = state.myRoom && state.myRoom.id === room.id;
    const looked = state.inspectedRoomId === room.id;
    const wool = WOOL[index % WOOL.length];

    ctx.fillStyle = '#6b4423';
    ctx.fillRect(cx - 10, cy - 8, 20, 16);
    ctx.fillStyle = wool;
    ctx.fillRect(cx - 6, cy - 5, 12, 10);

    const seats = Math.max(1, room.member_ids.length);
    for (let i = 0; i < seats; i++) {
      const angle = (i / seats) * Math.PI * 2 - Math.PI / 2;
      const sx = cx + Math.cos(angle) * (1.15 * TILE);
      const sy = cy + Math.sin(angle) * (1.15 * TILE * 0.85);
      ctx.fillStyle = '#5a3a22';
      ctx.fillRect(sx - 7, sy - 3, 14, 6);
      ctx.fillStyle = '#3e2916';
      ctx.fillRect(sx - 7, sy + 2, 14, 2);
    }

    if (room.meetup) {
      ctx.fillStyle = '#4a4a4a';
      ctx.fillRect(cx - 3, cy - 6, 6, 8);
    } else {
      const flicker = REDUCE_MOTION ? 0 : Math.sin(now / 120 + index) * 2;
      ctx.fillStyle = '#f08a24';
      ctx.fillRect(cx - 3, cy - 12 - flicker, 6, 10);
      ctx.fillStyle = '#ffe28a';
      ctx.fillRect(cx - 1, cy - 16 - flicker, 3, 6);
    }

    if (mine || looked) {
      ctx.fillStyle = mine ? '#ffe56a' : '#f2d04b';
      [[-14, -12], [10, -12], [-14, 8], [10, 8]].forEach(([dx, dy]) => {
        ctx.fillRect(cx + dx, cy + dy, 5, 5);
      });
    }

    const tag = room.shared_interests?.[0] ? room.shared_interests[0].slice(0, 8) : room.id;
    drawSign(cx, cy - 18, mine ? `YOU ${room.id}` : String(tag).toUpperCase());
  });
}

function pxRect(x, y, w, h, color) {
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

function drawAvatars() {
  const demoIds = new Set(state.world.synthetic_ids || []);
  const sorted = Array.from(state.avatars.values()).sort((a, b) => a.y - b.y);
  sorted.forEach((av) => {
    const att = av.profile;
    if (!att) return;
    const isMe = state.me && att.id === state.me.id;
    const isSelected = state.selectedAttendeeId === att.id;
    if (isMe) {
      ctx.fillStyle = '#ffe56a';
      ctx.fillRect(av.x - 8, av.y - 3, 16, 4);
    } else if (isSelected) {
      ctx.fillStyle = '#f4fbff';
      ctx.fillRect(av.x - 8, av.y - 3, 16, 4);
    }
    drawSteve(av);

    const isDemo = demoIds.has(att.id);
    const label = isDemo ? `${att.nickname} · demo` : att.nickname;
    const showName = isMe || isSelected || state.camera.zoom >= 1.15;
    if (showName) {
      ctx.font = '700 11px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(0,0,0,0.85)';
      ctx.strokeText(label, av.x, av.y - 40);
      ctx.fillStyle = isMe ? '#ffe56a' : isDemo ? '#b6c2d4' : '#ffffff';
      ctx.fillText(label, av.x, av.y - 40);
    }

    if (av.chatText) {
      ctx.font = '700 10px Inter, sans-serif';
      const bw = ctx.measureText(av.chatText).width + 10;
      const by = av.y - 56;
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(av.x - bw / 2 - 1, by - 1, bw + 2, 16);
      ctx.fillStyle = '#f4fbff';
      ctx.fillRect(av.x - bw / 2, by, bw, 14);
      ctx.fillStyle = '#1a1a1a';
      ctx.textAlign = 'center';
      ctx.fillText(av.chatText, av.x, by + 7);
    }
  });
}

function drawSteve(av) {
  const att = av.profile;
  const h = hashStr(att.id);
  const skin = SKINS[h % SKINS.length];
  const hair = HAIR[(h >> 4) % HAIR.length];
  const shirt = ROLE_COLORS[att.role] || '#3b6fd6';
  const swing = av.isWalking && !REDUCE_MOTION ? Math.sin(av.walkPhase) * 3 : 0;
  const bob = av.isWalking && !REDUCE_MOTION ? Math.abs(Math.sin(av.walkPhase * 2)) * 1.4 : 0;

  ctx.save();
  ctx.translate(av.x, av.y + bob);
  ctx.scale(1.25, 1.25);
  ctx.fillStyle = 'rgba(0,0,0,0.28)';
  ctx.beginPath();
  ctx.ellipse(0, 1, 8, 3, 0, 0, Math.PI * 2);
  ctx.fill();
  if (av.facing < 0) ctx.scale(-1, 1);

  pxRect(-5, -10 + swing, 4, 8, '#3a3a6e');
  pxRect(1, -10 - swing, 4, 8, '#3a3a6e');
  pxRect(-5, -4 + swing, 4, 2, '#4a3728');
  pxRect(1, -4 - swing, 4, 2, '#4a3728');
  pxRect(-5, -20, 10, 10, shirt);
  pxRect(-9, -20 - swing, 4, 8, skin);
  pxRect(5, -20 + swing, 4, 8, skin);
  pxRect(-6, -32, 12, 12, skin);
  ctx.fillStyle = hair;
  ctx.fillRect(-5, -31, 10, 4);
  ctx.fillRect(-5, -31, 2, 7);
  ctx.fillStyle = '#1a1a1a';
  ctx.fillRect(0, -26, 2, 2);
  ctx.fillRect(4, -26, 2, 2);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(1, -26, 1, 1);
  ctx.fillRect(5, -26, 1, 1);
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

// --- Canvas Mouse Pan, Zoom & Click Hit-Testing ---
const pointers = new Map(); // pointerId -> {x, y}; two active = pinch
let pinchDist = 0;

canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 1) {
    state.camera.dragging = true;
    state.camera.moved = false;
    state.camera.dragStartX = e.clientX - state.camera.x;
    state.camera.dragStartY = e.clientY - state.camera.y;
  } else if (pointers.size === 2) {
    const [a, b] = Array.from(pointers.values());
    pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
    state.camera.moved = true; // never treat a pinch as a tap
  }
});

canvas.addEventListener('pointermove', (e) => {
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    const [a, b] = Array.from(pointers.values());
    const dist = Math.hypot(a.x - b.x, a.y - b.y);
    if (pinchDist > 0) {
      const rect = canvas.getBoundingClientRect();
      const mx = (a.x + b.x) / 2 - rect.left;
      const my = (a.y + b.y) / 2 - rect.top;
      const worldBefore = screenToWorld(mx, my);
      state.camera.zoom = Math.max(0.45, Math.min(2.2, state.camera.zoom * (dist / pinchDist)));
      state.camera.x = mx - worldBefore.x * state.camera.zoom;
      state.camera.y = my - worldBefore.y * state.camera.zoom;
    }
    pinchDist = dist;
    return;
  }
  if (!state.camera.dragging) return;
  const nx = e.clientX - state.camera.dragStartX;
  const ny = e.clientY - state.camera.dragStartY;
  if (Math.hypot(nx - state.camera.x, ny - state.camera.y) > 6) {
    state.camera.moved = true;
    state.camera.follow = false;
  }
  state.camera.x = nx;
  state.camera.y = ny;
});

function endPointer(e) {
  if (!pointers.has(e.pointerId)) return;
  pointers.delete(e.pointerId);
  pinchDist = 0;
  if (pointers.size > 0) {
    // one finger left after a pinch: re-anchor the pan so the map doesn't jump
    const [p] = Array.from(pointers.values());
    state.camera.dragStartX = p.x - state.camera.x;
    state.camera.dragStartY = p.y - state.camera.y;
    return;
  }
  const wasClick = !state.camera.moved && e.type === 'pointerup';
  state.camera.dragging = false;
  if (wasClick) handleCanvasClick(e);
}
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', endPointer);

canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const worldBefore = screenToWorld(mx, my);

  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  state.camera.zoom = Math.max(0.45, Math.min(2.2, state.camera.zoom * factor));

  state.camera.x = mx - worldBefore.x * state.camera.zoom;
  state.camera.y = my - worldBefore.y * state.camera.zoom;
}, { passive: false });

function handleCanvasClick(e) {
  const rect = canvas.getBoundingClientRect();
  const pt = screenToWorld(e.clientX - rect.left, e.clientY - rect.top);

  // 1. Check if user clicked an Avatar
  for (const av of Array.from(state.avatars.values()).reverse()) {
    if (Math.hypot(pt.x - av.x, pt.y - (av.y - 16)) <= 26) {
      state.selectedAttendeeId = av.id;
      showAvatarInspector(av.profile);
      // Also inspect their room if they are in one
      const room = state.world.rooms.find((r) => r.member_ids.includes(av.id));
      if (room) {
        state.inspectedRoomId = room.id;
        renderRightSidebar();
      }
      return;
    }
  }

  // 2. Check if user clicked a Virtual Room Pod
  for (const room of state.world.rooms) {
    const pod = state.roomPositions.get(room.id);
    if (!pod) continue;
    if (Math.hypot(pt.x - pod.x * TILE, pt.y - pod.y * TILE) <= 1.1 * TILE) {
      state.inspectedRoomId = room.id;
      hideInspector();
      renderRightSidebar();
      openPanel('panel-right');
      return;
    }
  }

  // 3. Check if user clicked a Physical Spot Zone
  for (const spot of state.world.spots) {
    const theme = SPOT_THEMES[spot.id] || { w: 4.2, h: 3.0 };
    const dx = Math.abs(pt.x - spot.x * TILE);
    const dy = Math.abs(pt.y - spot.y * TILE);
    if (dx <= (theme.w * TILE) / 2 && dy <= (theme.h * TILE) / 2) {
      state.selectedSpotId = spot.id;
      // If a room is meeting at this spot, show it in the right sidebar!
      const meetingRoom = state.world.rooms.find((r) => r.meetup && r.meetup.spot_id === spot.id);
      if (meetingRoom) {
        state.inspectedRoomId = meetingRoom.id;
        renderRightSidebar();
      }
      // If logged in, also walk user's avatar to the clicked spot
      if (state.me && state.avatars.has(state.me.id)) {
        const myAv = state.avatars.get(state.me.id);
        myAv.manualTarget = true;
        myAv.tx = pt.x;
        myAv.ty = pt.y;
      }
      return;
    }
  }

  // 4. Clicked open floor: if logged in, walk player's avatar to clicked floor point!
  hideInspector();
  if (state.me && state.avatars.has(state.me.id)) {
    const myAv = state.avatars.get(state.me.id);
    myAv.manualTarget = true;
    const tx = Math.max(TILE, Math.min((GRID_W - 1) * TILE, pt.x));
    const ty = Math.max(TILE, Math.min((GRID_H - 1) * TILE, pt.y));
    if (solidAt(tx, ty)) { showToast('Something is in the way.'); return; }
    myAv.tx = tx;
    myAv.ty = ty;
    state.camera.follow = true;
  }
}

function showAvatarInspector(profile) {
  const el = document.getElementById('map-inspector');
  const icon = ROLE_ICONS[profile.role] || '✨';
  const room = state.world.rooms.find((r) => r.member_ids.includes(profile.id));
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
      <strong>${icon} ${escapeHtml(profile.nickname)}</strong>
      <span class="role-badge">${escapeHtml(profile.role)}</span>
    </div>
    <p style="font-size:12px;color:#3a2a14;margin-bottom:6px;">"${escapeHtml(profile.one_liner)}"</p>
    <div class="tag-list">
      ${profile.interests.map((i) => `<span class="tag-chip">#${escapeHtml(i)}</span>`).join('')}
      ${room ? `<span class="badge badge-cyan">Room ${room.id}</span>` : ''}
    </div>
  `;
  el.classList.remove('hidden');
}

function hideInspector() {
  state.selectedAttendeeId = null;
  document.getElementById('map-inspector').classList.add('hidden');
}

// --- Keyboard Listeners for Walking ---
window.addEventListener('keydown', (e) => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (e.code === 'KeyE') runInteraction();
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyW', 'KeyA', 'KeyS', 'KeyD'].includes(e.code)) {
    state.keys.add(e.code);
  }
});

window.addEventListener('keyup', (e) => {
  state.keys.delete(e.code);
});

// --- UI Event Listeners ---
let sampleIdx = 0;
document.getElementById('btn-sample-persona').addEventListener('click', () => {
  const sample = SAMPLE_PERSONAS[sampleIdx % SAMPLE_PERSONAS.length];
  sampleIdx++;
  document.getElementById('input-nickname').value = sample.nickname;
  document.getElementById('input-about').value = sample.about;
  document.getElementById('input-contact').value = sample.contact;
});

const WORK_STEP_MS = 650;
function setOnboardStep(step) {
  state.onboardStep = step;
  document.getElementById('join-card').classList.toggle('hidden', step !== 'form');
  document.getElementById('onb-working').classList.toggle('hidden', step !== 'working');
  document.getElementById('onb-ready').classList.toggle('hidden', step !== 'ready');
  const order = ['form', 'working', 'ready'];
  document.querySelectorAll('#stepper li').forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle('active', i === order.indexOf(step));
    li.classList.toggle('done', i < order.indexOf(step));
  });
  updatePhase();
}

async function animateWorkList(untilDone) {
  const items = Array.from(document.querySelectorAll('#work-list li'));
  items.forEach((li) => li.classList.remove('active', 'done'));
  let i = 0;
  // Advance a step at a time; hold on the last one until the API call resolves.
  while (i < items.length) {
    items[i].classList.add('active');
    const stepWait = new Promise((r) => setTimeout(r, WORK_STEP_MS));
    if (i === items.length - 1) await Promise.all([stepWait, untilDone]);
    else await stepWait;
    items[i].classList.remove('active');
    items[i].classList.add('done');
    i += 1;
  }
}

document.getElementById('join-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn-join');
  const nickname = document.getElementById('input-nickname').value.trim();
  const about = document.getElementById('input-about').value.trim();
  const contact = document.getElementById('input-contact').value.trim();
  if (!nickname) return;

  btn.disabled = true;
  setOnboardStep('working');
  const call = api('/api/join', {
    method: 'POST',
    body: JSON.stringify({ nickname, about, contact: contact || null }),
  });
  call.catch(() => {}); // handled below; avoids an unhandled-rejection warning while animating
  try {
    await animateWorkList(call);
    const res = await call;
    state.token = res.token;
    state.me = res.me;
    localStorage.setItem('ena_token', res.token);

    document.getElementById('onb-nick').textContent = res.me.nickname;
    document.getElementById('onb-oneliner').textContent = `"${res.me.one_liner}"`;
    const tags = document.getElementById('onb-tags');
    tags.innerHTML = '';
    [...(res.me.interests || []), ...(res.me.goals || [])].forEach((t) => {
      const span = document.createElement('span');
      span.className = 'tag-chip';
      span.textContent = t;
      tags.appendChild(span);
    });
    await refreshState();
    setOnboardStep('ready');
  } catch (err) {
    showToast(`Join failed: ${err.message}`);
    setOnboardStep('form');
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('btn-enter').addEventListener('click', () => {
  setOnboardStep('form'); // me is set, so the phase flips to play
  const myAv = state.me && state.avatars.get(state.me.id);
  state.camera.follow = true;
  if (myAv) panToPixel(myAv.x, myAv.y, isMobile() ? 0.9 : 1.1);
  showToast(`Welcome ${state.me.nickname}! Your avatar is on the floor.`);
});

document.getElementById('btn-leave').addEventListener('click', () => {
  state.token = null;
  state.me = null;
  state.myRoom = null;
  state.connections = [];
  localStorage.removeItem('ena_token');
  renderLeftSidebar();
  renderRightSidebar();
  setOnboardStep('form');
});

document.getElementById('btn-vote-meet').addEventListener('click', async () => {
  const btn = document.getElementById('btn-vote-meet');
  btn.disabled = true;
  try {
    const updatedRoom = await api('/api/me/room/meet', { method: 'POST' });
    state.myRoom = updatedRoom;
    if (updatedRoom.meetup) {
      showToast(`📍 Quorum reached! Booked ${updatedRoom.meetup.spot_name} — walking over!`);
    } else {
      showToast(`Vote recorded (${updatedRoom.votes}/${updatedRoom.votes_needed}). Click "⚡ Simulate Votes" in top bar to have bot roommates vote!`);
    }
    await refreshState();
  } catch (err) {
    showToast(`Vote error: ${err.message}`);
    btn.disabled = false;
  }
});

document.getElementById('btn-back-my-room').addEventListener('click', () => {
  state.inspectedRoomId = null;
  renderRightSidebar();
});

// --- Organiser / Demo Toolbar Actions ---
document.getElementById('btn-seed').addEventListener('click', async () => {
  const btn = document.getElementById('btn-seed');
  btn.disabled = true;
  try {
    const res = await api('/api/demo/seed', {
      method: 'POST',
      body: JSON.stringify({ count: 15, use_llm: false }),
    });
    showToast(`Spawned ${res.added} synthetic attendees (${res.attendees} total on floor).`);
    await refreshState();
  } catch (err) {
    showToast(`Seed failed: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

async function triggerNextRound() {
  const btns = document.querySelectorAll('.js-next-round');
  btns.forEach((b) => { b.disabled = true; });
  setBanner('Matchmaker & Gemini Room Host grouping attendees into rooms...');
  try {
    // If fewer than 4 people are in the venue, seed bots automatically so a round is meaningful
    if (state.world.attendees.length < 4) {
      await api('/api/demo/seed', {
        method: 'POST',
        body: JSON.stringify({ count: Math.max(5, 15 - state.world.attendees.length), use_llm: false }),
      });
    }
    const res = await api('/api/demo/round', { method: 'POST' });
    state.inspectedRoomId = null;
    showToast(`🎯 Round ${res.round} started! ${res.rooms} rooms formed — avatars walking to pods.`);
    await refreshState();
  } catch (err) {
    showToast(`Start round failed: ${err.message}`);
  } finally {
    setBanner(null);
    btns.forEach((b) => { b.disabled = false; });
  }
}

document.querySelectorAll('.js-next-round').forEach((b) => b.addEventListener('click', () => {
  document.getElementById('organiser-drawer').classList.add('hidden');
  triggerNextRound();
}));

document.getElementById('btn-quick-populate').addEventListener('click', async () => {
  await triggerNextRound();
});

document.getElementById('btn-simulate').addEventListener('click', async () => {
  const btn = document.getElementById('btn-simulate');
  btn.disabled = true;
  try {
    if (state.world.round === 0) {
      showToast('Starting Round 1 first so rooms can vote...');
      await triggerNextRound();
    }
    const res = await api('/api/demo/simulate', {
      method: 'POST',
      body: JSON.stringify({ meet_prob: 0.7, like_prob: 0.8 }),
    });
    showToast(`⚡ Bots cast ${res.votes_cast} meetup votes (${res.meetups_this_round} spots booked) & ${res.likes_cast} likes!`);
    await refreshState();
  } catch (err) {
    showToast(`Simulation failed: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('btn-reset').addEventListener('click', async () => {
  const adminToken = window.prompt('Organiser token (ADMIN_TOKEN) to reset the event:');
  if (!adminToken) return;
  try {
    await api('/api/demo/reset', { method: 'POST', headers: { 'X-Admin-Token': adminToken } });
  } catch (err) {
    showToast(err.status === 403 ? 'Reset refused: wrong organiser token.' : `Reset failed: ${err.message}`);
    return;
  }
  state.token = null;
  state.me = null;
  state.myRoom = null;
  state.inspectedRoomId = null;
  state.connections = [];
  state.avatars.clear();
  localStorage.removeItem('ena_token');
  showToast('Venue floor reset.');
  setOnboardStep('form');
  await refreshState();
});

// --- Map Camera Controls ---
document.getElementById('btn-zoom-in').addEventListener('click', () => {
  state.camera.zoom = Math.min(2.2, state.camera.zoom * 1.18);
});
document.getElementById('btn-zoom-out').addEventListener('click', () => {
  state.camera.zoom = Math.max(0.45, state.camera.zoom / 1.18);
});
document.getElementById('btn-fit-map').addEventListener('click', () => {
  state.camera.follow = false;
  fitVenueCamera();
});
document.getElementById('btn-center-me').addEventListener('click', () => {
  if (state.me && state.avatars.has(state.me.id)) {
    const av = state.avatars.get(state.me.id);
    state.camera.follow = true;
    panToPixel(av.x, av.y, isMobile() ? 0.95 : 1.25);
  } else {
    showToast('Join the venue on the left to spawn your avatar first!');
  }
});
document.getElementById('btn-rejoin-group').addEventListener('click', () => {
  if (state.me && state.avatars.has(state.me.id)) {
    const av = state.avatars.get(state.me.id);
    av.manualTarget = false;
    syncAvatars();
    showToast('Walking back to your assigned group!');
  }
});

window.addEventListener('resize', () => {
  resizeCanvas();
  fitVenueCamera();
});

// --- Touch joystick ---
(function initJoystick() {
  const base = document.getElementById('joystick');
  const knob = base.querySelector('.joy-knob');
  let pid = null;
  const R = 44;
  function move(e) {
    const r = base.getBoundingClientRect();
    let dx = e.clientX - (r.left + r.width / 2);
    let dy = e.clientY - (r.top + r.height / 2);
    const d = Math.hypot(dx, dy);
    if (d > R) { dx = (dx / d) * R; dy = (dy / d) * R; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    state.joy.x = dx / R;
    state.joy.y = dy / R;
  }
  function end(e) {
    if (e.pointerId !== pid) return;
    pid = null;
    state.joy.x = 0;
    state.joy.y = 0;
    knob.style.transform = '';
  }
  base.addEventListener('pointerdown', (e) => { pid = e.pointerId; base.setPointerCapture(pid); move(e); });
  base.addEventListener('pointermove', (e) => { if (e.pointerId === pid) move(e); });
  base.addEventListener('pointerup', end);
  base.addEventListener('pointercancel', end);
})();

// --- Proximity prompt: walk up to a room or meetup spot and get a one-tap action ---
const interactEl = document.getElementById('interact-hint');
let interactTarget = null;
let lastHintCheck = 0;

function updateInteractHint(now) {
  if (now - lastHintCheck < 180) return;
  lastHintCheck = now;
  const me = state.me && state.avatars.get(state.me.id);
  let best = null;
  if (me && document.body.dataset.phase === 'play') {
    const px = me.x / TILE;
    const py = me.y / TILE;
    const occupancy = new Map();
    state.world.rooms.forEach((r) => {
      if (r.meetup) occupancy.set(r.meetup.spot_id, (occupancy.get(r.meetup.spot_id) || 0) + r.member_ids.length);
    });
    (state.world.spots || []).forEach((spot) => {
      const d = Math.hypot(px - spot.x, py - spot.y);
      if (d < 3.4 && (!best || d < best.d)) {
        const theme = SPOT_THEMES[spot.id] || { icon: '📍' };
        best = { d, kind: 'spot', id: spot.id, label: `${theme.icon} ${spot.name} · ${occupancy.get(spot.id) || 0}/${spot.capacity}` };
      }
    });
    state.world.rooms.forEach((room) => {
      const pod = state.roomPositions.get(room.id);
      if (!pod) return;
      const d = Math.hypot(px - pod.x, py - pod.y);
      if (d < 2.6 && (!best || d < best.d)) {
        best = { d, kind: 'room', id: room.id, label: `Room ${room.id} · ${room.member_ids.length} people` };
      }
    });
  }
  const key = best ? `${best.kind}:${best.id}` : '';
  if (key !== (interactTarget ? `${interactTarget.kind}:${interactTarget.id}` : '')) {
    interactTarget = best;
    interactEl.classList.toggle('hidden', !best);
    if (best) interactEl.querySelector('.hint-text').textContent = best.label;
  }
}

function runInteraction() {
  if (!interactTarget) return;
  if (interactTarget.kind === 'room') {
    state.inspectedRoomId = interactTarget.id;
    renderRightSidebar();
    openPanel('panel-right');
  } else {
    state.selectedSpotId = interactTarget.id;
    openPanel('panel-left');
  }
}
interactEl.addEventListener('click', runInteraction);

// --- Phase (onboard -> play) & floating panels ---
const isMobile = () => window.matchMedia('(max-width: 760px)').matches;

function openPanel(id, open = true) {
  const panels = ['panel-left', 'panel-right'];
  panels.forEach((pid) => {
    const el = document.getElementById(pid);
    // On phones only one sheet is open at a time.
    const next = pid === id ? open : (open && isMobile() ? false : el.classList.contains('open'));
    el.classList.toggle('open', next);
    const btn = document.querySelector(`.dock-btn[data-panel="${pid}"]`);
    btn.classList.toggle('active', next);
    btn.setAttribute('aria-pressed', String(next));
  });
  document.body.classList.toggle('sheet-open', panels.some((pid) => document.getElementById(pid).classList.contains('open')));
}

function updatePhase() {
  const next = state.me && state.onboardStep === 'form' ? 'play' : 'onboard';
  const prev = document.body.dataset.phase;
  if (prev === next) {
    syncRoomPanel();
    return;
  }
  document.body.dataset.phase = next;
  if (next === 'play') {
    // The game takes over: refit the camera for the full-bleed map.
    resizeCanvas();
    if (isMobile()) { openPanel('panel-right', false); openPanel('panel-left', false); }
  }
  syncRoomPanel();
}

// Slide the room panel open the first time the player lands in a room.
function syncRoomPanel() {
  const rid = state.myRoom && state.myRoom.id;
  if (rid && rid !== state.lastRoomId && document.body.dataset.phase === 'play') {
    openPanel('panel-right', true);
  }
  state.lastRoomId = rid || null;
}

document.querySelectorAll('.dock-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const el = document.getElementById(btn.dataset.panel);
    openPanel(btn.dataset.panel, !el.classList.contains('open'));
  });
});

document.querySelectorAll('.panel-close').forEach((btn) => {
  btn.addEventListener('click', () => openPanel(btn.dataset.close, false));
});
window.addEventListener('keydown', (e) => {
  if (e.code === 'Escape') {
    openPanel('panel-left', false);
    openPanel('panel-right', false);
    setToolsOpen(false);
  }
});
// On phones a tap on the bare map tucks the sheet away.
canvas.addEventListener('pointerdown', () => {
  if (isMobile()) { openPanel('panel-left', false); openPanel('panel-right', false); }
});

function setToolsOpen(open) {
  document.getElementById('organiser-drawer').classList.toggle('hidden', !open);
  document.getElementById('btn-tools').setAttribute('aria-expanded', String(open));
}

document.getElementById('btn-tools').addEventListener('click', () => {
  setToolsOpen(document.getElementById('organiser-drawer').classList.contains('hidden'));
});

// Dismiss on any outside press (capture phase so the map's own handlers can't swallow it)
// and after choosing an action inside the drawer.
document.addEventListener('pointerdown', (e) => {
  const drawer = document.getElementById('organiser-drawer');
  if (drawer.classList.contains('hidden')) return;
  if (drawer.contains(e.target) || e.target.closest('#btn-tools')) return;
  setToolsOpen(false);
}, true);
document.getElementById('organiser-drawer').addEventListener('click', (e) => {
  if (e.target.closest('button')) setToolsOpen(false);
});

// --- Initialize App ---
(async function init() {
  resizeCanvas();
  fitVenueCamera();
  await refreshState();
  updatePhase();
  requestAnimationFrame(tickAndDraw);
  setInterval(refreshState, 3500);
})();
