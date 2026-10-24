import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { ActionItem, MeetingSession, UserProfile } from '../shared/types.ts';
import { STORAGE_KEYS } from '../shared/constants.ts';
import { Header } from './components/Header.tsx';
import { SummaryTab } from './components/SummaryTab.tsx';
import { TodoListTab } from './components/TodoListTab.tsx';
import { AddTaskModal } from './components/AddTaskModal.tsx';
import { DeadlinePromptModal } from './components/DeadlinePromptModal.tsx';
import { FileText, CheckSquare, Settings } from 'lucide-react';
import './style.css';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'summary' | 'todos' | 'settings'>('todos');
  const [session, setSession] = useState<MeetingSession | null>(null);
  const [tasks, setTasks] = useState<ActionItem[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);

  // Loading & Modal States
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [isExtractingActions, setIsExtractingActions] = useState(false);
  const [isSyncingDrive, setIsSyncingDrive] = useState(false);
  const [isAddTaskOpen, setIsAddTaskOpen] = useState(false);
  const [promptTask, setPromptTask] = useState<ActionItem | null>(null);

  // Settings State
  const [backendUrl, setBackendUrl] = useState('http://localhost:8000');
  const [modelName, setModelName] = useState('gemma2:9b');

  // Load state from chrome storage
  const loadState = async () => {
    const data = await chrome.storage.local.get([
      STORAGE_KEYS.ACTIVE_MEETING,
      STORAGE_KEYS.TASKS,
      STORAGE_KEYS.USER_PROFILE,
      STORAGE_KEYS.SETTINGS,
    ]);

    if (data[STORAGE_KEYS.ACTIVE_MEETING]) {
      setSession(data[STORAGE_KEYS.ACTIVE_MEETING]);
    }
    if (data[STORAGE_KEYS.TASKS]) {
      setTasks(data[STORAGE_KEYS.TASKS]);
    }
    if (data[STORAGE_KEYS.USER_PROFILE]) {
      setProfile(data[STORAGE_KEYS.USER_PROFILE]);
    }
    if (data[STORAGE_KEYS.SETTINGS]) {
      setBackendUrl(data[STORAGE_KEYS.SETTINGS].backendUrl || 'http://localhost:8000');
      setModelName(data[STORAGE_KEYS.SETTINGS].modelName || 'gemma2:9b');
    }
  };

  useEffect(() => {
    loadState();

    // Listen for storage changes from background worker or content script
    const handleStorageChange = (changes: { [key: string]: chrome.storage.StorageChange }) => {
      if (changes[STORAGE_KEYS.ACTIVE_MEETING]) {
        setSession(changes[STORAGE_KEYS.ACTIVE_MEETING].newValue);
      }
      if (changes[STORAGE_KEYS.TASKS]) {
        setTasks(changes[STORAGE_KEYS.TASKS].newValue || []);
      }
      if (changes[STORAGE_KEYS.USER_PROFILE]) {
        setProfile(changes[STORAGE_KEYS.USER_PROFILE].newValue);
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);
    return () => chrome.storage.onChanged.removeListener(handleStorageChange);
  }, []);

  // Handlers
  const handleSignIn = () => {
    chrome.runtime.sendMessage({ action: 'SIGN_IN_GOOGLE' }, (res) => {
      if (res?.success && res.profile) {
        setProfile(res.profile);
      }
    });
  };

  const handleSignOut = () => {
    chrome.runtime.sendMessage({ action: 'SIGN_OUT_GOOGLE' }, () => {
      setProfile(null);
    });
  };

  const handleSyncDrive = () => {
    setIsSyncingDrive(true);
    chrome.runtime.sendMessage({ action: 'TRIGGER_SYNC_DRIVE' }, (res) => {
      setIsSyncingDrive(false);
      if (res?.success && res.driveUrl && session) {
        setSession({ ...session, driveUrl: res.driveUrl });
      } else if (res?.error) {
        alert(`Google Drive sync: ${res.error}`);
      }
    });
  };

  const handleGenerateSummary = () => {
    setIsGeneratingSummary(true);
    chrome.runtime.sendMessage({ action: 'GENERATE_SUMMARY' }, (res) => {
      setIsGeneratingSummary(false);
      if (res?.success && res.summary && session) {
        setSession({ ...session, summary: res.summary });
        setActiveTab('summary');
      } else if (res?.error) {
        alert(res.error);
      }
    });
  };

  const handleExtractActions = () => {
    setIsExtractingActions(true);
    chrome.runtime.sendMessage({ action: 'EXTRACT_ACTIONS' }, (res) => {
      setIsExtractingActions(false);
      if (res?.success && res.actionItems) {
        loadState();
        setActiveTab('todos');
      } else if (res?.error) {
        alert(res.error);
      }
    });
  };

  const handleUpdateTask = (taskId: string, updates: Partial<ActionItem>) => {
    chrome.runtime.sendMessage({
      action: 'UPDATE_TASK',
      payload: { taskId, updates },
    });
    // Optimistic UI update
    setTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, ...updates } : t))
    );
  };

  const handleAddTask = (newTaskData: any) => {
    chrome.runtime.sendMessage({
      action: 'ADD_MANUAL_TASK',
      payload: newTaskData,
    });
  };

  const handleSaveDeadline = (taskId: string, deadline: string) => {
    handleUpdateTask(taskId, { deadline });
  };

  const handleSaveSettings = () => {
    chrome.storage.local.set({
      [STORAGE_KEYS.SETTINGS]: {
        backendUrl,
        modelName,
        autoSaveToDrive: true,
        autoCalendarSync: true,
        emailNudgesEnabled: true,
      },
    });
    alert('Settings updated successfully!');
  };

  const pendingCount = tasks.filter((t) => t.status === 'pending').length;

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 text-slate-800">
      <Header
        session={session}
        profile={profile}
        onSignIn={handleSignIn}
        onSignOut={handleSignOut}
        onSyncDrive={handleSyncDrive}
        isSyncingDrive={isSyncingDrive}
      />

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-200 bg-white px-2 sticky top-[82px] z-10">
        <button
          onClick={() => setActiveTab('todos')}
          className={`flex-1 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 border-b-2 transition-all ${
            activeTab === 'todos'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <CheckSquare size={14} />
          <span>Action Items</span>
          {pendingCount > 0 && (
            <span className="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0.2 rounded-full font-bold">
              {pendingCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('summary')}
          className={`flex-1 py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 border-b-2 transition-all ${
            activeTab === 'summary'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText size={14} />
          <span>Summary</span>
        </button>

        <button
          onClick={() => setActiveTab('settings')}
          className={`px-3 py-2.5 text-xs font-semibold flex items-center justify-center border-b-2 transition-all ${
            activeTab === 'settings'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-400 hover:text-slate-700'
          }`}
        >
          <Settings size={14} />
        </button>
      </div>

      {/* Main Tab Content */}
      <main className="flex-1 p-3.5 pb-16">
        {activeTab === 'todos' && (
          <TodoListTab
            tasks={tasks}
            onUpdateTask={handleUpdateTask}
            onExtractActions={handleExtractActions}
            onOpenAddTask={() => setIsAddTaskOpen(true)}
            onPromptDeadline={(t) => setPromptTask(t)}
            isExtracting={isExtractingActions}
            transcriptCount={session?.transcript?.length || 0}
          />
        )}

        {activeTab === 'summary' && (
          <SummaryTab
            session={session}
            onGenerateSummary={handleGenerateSummary}
            isGenerating={isGeneratingSummary}
          />
        )}

        {activeTab === 'settings' && (
          <div className="bg-white rounded-xl p-4 border border-slate-200/90 shadow-xs space-y-3.5 text-xs">
            <h3 className="font-bold text-slate-800 text-sm">Agent & Model Settings</h3>

            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                ADK & A2A Backend Server URL
              </label>
              <input
                type="text"
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                placeholder="http://localhost:8000"
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                Open Source Model (Gemma)
              </label>
              <input
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="gemma2:9b"
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs"
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Supports Ollama model tag, vLLM endpoint, or local Gemma model identifier.
              </p>
            </div>

            <div className="pt-2">
              <button
                onClick={handleSaveSettings}
                className="w-full bg-slate-800 hover:bg-slate-900 text-white font-semibold py-2 rounded-lg text-xs transition-colors"
              >
                Save Settings
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Modals */}
      <AddTaskModal
        isOpen={isAddTaskOpen}
        onClose={() => setIsAddTaskOpen(false)}
        onAddTask={handleAddTask}
        currentMeetingTitle={session?.title}
        defaultOwner={profile?.name || 'Me'}
      />

      <DeadlinePromptModal
        isOpen={!!promptTask}
        task={promptTask}
        onClose={() => setPromptTask(null)}
        onSaveDeadline={handleSaveDeadline}
      />
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

