import React from 'react';
import { MeetingSession, UserProfile } from '../../shared/types.ts';
import { Cloud, CheckCircle, Video, LogIn, LogOut, ExternalLink } from 'lucide-react';

interface HeaderProps {
  session: MeetingSession | null;
  profile: UserProfile | null;
  onSignIn: () => void;
  onSignOut: () => void;
  onSyncDrive: () => void;
  isSyncingDrive: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  session,
  profile,
  onSignIn,
  onSignOut,
  onSyncDrive,
  isSyncingDrive,
}) => {
  return (
    <header className="bg-white border-b border-slate-200 px-4 py-3 sticky top-0 z-20 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-md shadow-blue-200">
            M
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-900 leading-tight">MeetingMind AI</h1>
            <p className="text-[10px] text-slate-500 font-medium">Gemma • ADK • A2A • MCP</p>
          </div>
        </div>

        {/* User Profile / Auth */}
        <div className="flex items-center gap-2">
          {profile?.isSignedIn ? (
            <div className="flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 py-1 px-2 rounded-full transition-colors">
              {profile.picture ? (
                <img
                  src={profile.picture}
                  alt={profile.name}
                  className="w-5 h-5 rounded-full object-cover"
                />
              ) : (
                <div className="w-5 h-5 rounded-full bg-blue-500 text-white text-[10px] flex items-center justify-center">
                  {profile.name.charAt(0)}
                </div>
              )}
              <span className="text-xs font-medium text-slate-700 max-w-[90px] truncate">
                {profile.name}
              </span>
              <button
                onClick={onSignOut}
                title="Sign out"
                className="text-slate-400 hover:text-red-500 ml-0.5 p-0.5"
              >
                <LogOut size={12} />
              </button>
            </div>
          ) : (
            <button
              onClick={onSignIn}
              className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 text-white text-xs px-2.5 py-1 rounded-md font-medium transition-colors shadow-sm"
            >
              <LogIn size={13} />
              Sign in with Gmail
            </button>
          )}
        </div>
      </div>

      {/* Meeting Context Bar */}
      <div className="flex items-center justify-between bg-slate-50 border border-slate-200/80 rounded-lg px-2.5 py-1.5 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <Video size={13} className="text-slate-500 shrink-0" />
          <span className="font-semibold text-slate-800 truncate" title={session?.title || 'Waiting for meeting...'}>
            {session?.title || 'No active meeting detected'}
          </span>
          {session?.platform && (
            <span className="uppercase text-[9px] font-bold tracking-wider px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
              {session.platform}
            </span>
          )}
        </div>

        {/* Google Drive Status */}
        <div className="flex items-center gap-1 shrink-0 ml-2">
          {session?.driveUrl ? (
            <a
              href={session.driveUrl}
              target="_blank"
              rel="noreferrer"
              title="Open notes in Google Drive"
              className="flex items-center gap-1 text-emerald-600 hover:text-emerald-700 text-[11px] font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200"
            >
              <CheckCircle size={12} />
              Drive
              <ExternalLink size={10} />
            </a>
          ) : (
            <button
              onClick={onSyncDrive}
              disabled={isSyncingDrive || !session}
              title="Save notes and action items to Google Drive"
              className="flex items-center gap-1 text-slate-600 hover:text-blue-600 disabled:opacity-50 text-[11px] font-medium bg-white px-2 py-0.5 rounded border border-slate-200 hover:border-blue-300 transition-colors"
            >
              <Cloud size={12} className={isSyncingDrive ? 'animate-pulse text-blue-500' : ''} />
              {isSyncingDrive ? 'Saving...' : 'Sync to Drive'}
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

