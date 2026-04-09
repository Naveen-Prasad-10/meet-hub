/* ════════════════════════════════════════════
   MeetHub — Full Operational Logic
   ════════════════════════════════════════════ */

const API = 'http://localhost:8000';

// ─── State ───
const state = {
  meetings: [],
  currentMeeting: null,
  uploadedFiles: [],
};

// ─── DOM Helpers ───
const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

// ─── UI Transitions ───
function switchView(viewName) {
  $$('.view-section').forEach(v => v.classList.add('hidden'));
  $(`view-${viewName}`).classList.remove('hidden');
  
  if (viewName === 'dashboard') {
    loadMeetings();
  } else if (viewName === 'calendar-section') {
    renderGlobalCalendar();
  }
}

$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    switchView(btn.dataset.target);
  });
});

$('btn-back').addEventListener('click', () => {
  switchView('dashboard');
});

// ─── API Helpers ───
async function apiPost(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error('Fetch failed');
  return res.json();
}

function toast(message, type = 'info') {
  const container = $('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.style.backgroundColor = '#121212';
  el.style.color = '#fff';
  el.style.padding = '12px 24px';
  el.style.border = '1px solid #fff';
  el.style.marginBottom = '10px';
  el.style.fontWeight = '600';
  el.style.fontSize = '0.8rem';
  el.style.textTransform = 'uppercase';
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ─── Dashboard Loading ───
async function loadMeetings() {
  try {
    const meetings = await apiGet('/meetings');
    state.meetings = meetings;
    renderDashboard(meetings);
  } catch (err) {
    toast('Error loading dashboard: ' + err.message, 'error');
  }
}

function renderDashboard(meetings) {
  const grid = $('meeting-grid');
  grid.innerHTML = '';
  
  if (meetings.length === 0) {
    grid.innerHTML = '<div class="empty-state">No meetings processed yet. Click "Add Meeting" to start.</div>';
    return;
  }

  meetings.forEach(m => {
    const card = document.createElement('div');
    card.className = 'meeting-card';
    card.innerHTML = `
      <h3>${m.title}</h3>
      <div class="card-meta">📅 ${new Date(m.date).toLocaleDateString()} • 🔊 ${JSON.parse(m.speakers).length} Speakers</div>
      <div class="card-stats">
        <span>${JSON.parse(m.processed_data).action_items.length} Action Items</span>
      </div>
      <button class="btn-card-view" data-id="${m.id}">View Results</button>
    `;
    card.querySelector('button').addEventListener('click', () => {
      showMeetingDetail(m);
    });
    grid.appendChild(card);
  });

  const totalActions = meetings.reduce((acc, m) => acc + JSON.parse(m.processed_data).action_items.length, 0);
  $('global-stats').innerHTML = `
    <div class="stat-mini"><span>${meetings.length}</span> Meetings</div>
    <div class="stat-mini"><span>${totalActions}</span> Action Items</div>
  `;
}

async function renderGlobalCalendar() {
  const grid = $('calendar-grid');
  grid.innerHTML = '<div class="loading-mini">Syncing calendar...</div>';

  try {
    let events = await apiGet('/calendar');

    // If empty, try syncing from saved meetings first
    if (events.length === 0) {
      const syncResult = await apiPost('/calendar/sync', {});
      if (syncResult.events_created > 0) {
        toast(`Synced ${syncResult.events_created} event(s) from saved meetings.`, 'success');
        events = await apiGet('/calendar');
      }
    }

    grid.innerHTML = '';

    if (events.length === 0) {
      // Check if there are meetings at all — guide user accordingly
      const meetings = state.meetings.length > 0
        ? state.meetings
        : await apiGet('/meetings');

      if (meetings.length === 0) {
        grid.innerHTML = `
          <div class="empty-state">
            <p>No scheduled events yet.</p>
            <p style="margin-top:8px;opacity:0.6;font-size:0.85rem;">
              Process a transcript via <strong>Add Meeting</strong> — action items will auto-appear here.
            </p>
          </div>`;
      } else {
        grid.innerHTML = `
          <div class="empty-state">
            <p>No action items found in saved meetings.</p>
            <p style="margin-top:8px;opacity:0.6;font-size:0.85rem;">
              Items are populated from transcripts that contain assignable action items.
            </p>
          </div>`;
      }
      return;
    }

    events.forEach(e => {
      const card = document.createElement('div');
      card.className = 'calendar-card';
      card.innerHTML = `
        <div class="calendar-card-header">
          <div class="date-badge">${e.date}</div>
          <span class="priority-badge ${e.priority.toLowerCase()}">${e.priority}</span>
        </div>
        <div class="event-title">${e.title}</div>
        <div class="event-owner">${e.owner}</div>
        ${e.description ? `<div class="event-desc">${e.description}</div>` : ''}
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = '<div class="empty-state">Failed to load calendar events.</div>';
    toast('Calendar Error: ' + err.message, 'error');
  }
}


// ─── File Handling ───
const dropZone = $('drop-zone');
const fileInput = $('file-input');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => handleFiles(fileInput.files));

function handleFiles(files) {
  const list = $('file-list');
  for (const file of files) {
    if (!file.name.endsWith('.txt') && !file.name.endsWith('.vtt')) {
      toast(`${file.name} is not a supported format. Use .txt or .vtt.`, 'error');
      continue;
    }
    state.uploadedFiles.push(file);
    const item = document.createElement('div');
    item.className = 'file-item';
    item.textContent = `📄 ${file.name} (${Math.round(file.size / 1024)} KB)`;
    list.appendChild(item);
  }
}

// ─── Main Submit Event ───
$('btn-submit').addEventListener('click', async () => {
  let transcripts = [];
  
  if (state.uploadedFiles.length > 0) {
    toast(`Reading ${state.uploadedFiles.length} files...`);
    for (const file of state.uploadedFiles) {
      const text = await file.text();
      transcripts.push(text);
    }
  } else {
    const raw = $('transcript-input').value.trim();
    if (raw) transcripts.push(raw);
  }

  if (transcripts.length === 0) {
    toast('Please upload or enter a transcript.', 'error');
    return;
  }

  const btn = $('btn-submit');
  const spinner = $('spinner');
  btn.disabled = true;
  spinner.classList.remove('hidden');

  try {
    for (let i = 0; i < transcripts.length; i++) {
        const transcript = transcripts[i];
        toast(`Processing transcript ${i+1}/${transcripts.length}...`);
        
        const [processData, extractData] = await Promise.all([
          apiPost('/transcripts/process', { transcript }),
          apiPost('/transcripts/extract', { transcript })
        ]);

        const sentimentData = await apiPost('/meetings/sentiment', { 
          transcript: processData.clean_text 
        });

        const summaryData = await apiPost('/meetings/summary', {
          decisions: extractData.decisions,
          action_items: extractData.action_items,
          sentiment_timeline: sentimentData.timeline,
          speaker_summary: sentimentData.speaker_summary,
        });

        const meetingObject = {
          title: `Project Analysis ${new Date().toLocaleTimeString()}`,
          transcript: transcript,
          word_count: processData.metadata.word_count,
          speakers: processData.metadata.speakers,
          processed_data: {
            ...extractData,
            summary: summaryData.summary,
            sentiment: sentimentData
          }
        };

        await apiPost('/meetings', meetingObject);
    }

    toast('Analysis Complete! Returning to Dashboard.', 'success');
    state.uploadedFiles = [];
    $('file-list').innerHTML = '';
    $('transcript-input').value = '';
    switchView('dashboard');
  } catch (err) {
    toast(err.message, 'error');
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
  }
});

// ─── Detail View ───
function showMeetingDetail(m) {
  state.currentMeeting = m;
  const data = JSON.parse(m.processed_data);
  const speakersArr = JSON.parse(m.speakers);

  $('meeting-title').textContent = m.title;
  $('meeting-meta').textContent = `${new Date(m.date).toLocaleDateString()} • ${m.word_count} Words • ${speakersArr.length} Speakers`;
  
  // Render Main Points
  const hList = $('main-points-list');
  hList.innerHTML = '';
  const highlights = [
    { label: 'Key Decision', value: data.summary.key_decision },
    { label: 'Urgent Action', value: data.summary.urgent_action },
    { label: 'Vibe', value: data.summary.overall_sentiment }
  ];
  highlights.forEach(h => {
    if (!h.value) return;
    const div = document.createElement('div');
    div.className = 'highlight-item';
    div.innerHTML = `<h4>${h.label}</h4><p>${h.value}</p>`;
    hList.appendChild(div);
  });

  // Render Work
  const workBody = $('work-body');
  workBody.innerHTML = '';
  data.action_items.forEach(a => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${a.task}</td><td>${a.owner}</td><td>${a.deadline || '-'}</td>`;
    workBody.appendChild(tr);
  });

  // Render Sentiment Chart (Simplified color bars)
  const timeline = $('sentiment-timeline');
  timeline.innerHTML = '';
  if (data.sentiment && data.sentiment.timeline) {
    data.sentiment.timeline.forEach(t => {
      const bar = document.createElement('div');
      bar.className = `sentiment-bar ${t.sentiment.toLowerCase()}`;
      bar.title = `${t.speaker}: ${t.sentiment}`;
      bar.addEventListener('click', () => {
        toast(`${t.speaker}: "${t.segment}"`);
      });
      timeline.appendChild(bar);
    });
  }

  // Render Speaker Sentiment
  const sSentiment = $('speakers-sentiment');
  sSentiment.innerHTML = '';
  if (data.sentiment && data.sentiment.speaker_summary) {
    Object.keys(data.sentiment.speaker_summary).forEach(s => {
        const badge = document.createElement('div');
        badge.className = 'speaker-sentiment-badge';
        badge.innerHTML = `<strong>${s}</strong>: ${data.sentiment.speaker_summary[s]}`;
        sSentiment.appendChild(badge);
    });
  }

  // Reset Chat
  $('chat-history').innerHTML = '<div class="msg bot">Ask me anything about this meeting or project context.</div>';
  switchView('detail');
}

// ─── Chatbot Logic ───
$('btn-chat').addEventListener('click', async () => {
  const query = $('chat-input').value.trim();
  if (!query) return;

  appendMessage('user', query);
  $('chat-input').value = '';

  try {
    const res = await apiPost('/meetings/query', { 
      query, 
      context: [JSON.parse(state.currentMeeting.processed_data).summary.key_decision, state.currentMeeting.transcript] 
    });
    appendMessage('bot', res.answer);
  } catch (err) {
    appendMessage('bot', 'Error contacting intelligence: ' + err.message);
  }
});

function appendMessage(sender, text) {
  const hist = $('chat-history');
  const msg = document.createElement('div');
  msg.className = `msg ${sender}`;
  msg.textContent = text;
  hist.appendChild(msg);
  hist.scrollTop = hist.scrollHeight;
}

// ─── Export Logic ───
$('btn-export').addEventListener('click', () => {
  if (!state.currentMeeting) return;
  const data = JSON.parse(state.currentMeeting.processed_data);
  let csv = 'Task,Owner,Deadline,Priority\n';
  data.action_items.forEach(a => {
    csv += `"${a.task}","${a.owner}","${a.deadline || ''}","${a.priority}"\n`;
  });
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `meeting_actions_${state.currentMeeting.id}.csv`;
  a.click();
});

// ─── Init ───
loadMeetings();
switchView('dashboard');
