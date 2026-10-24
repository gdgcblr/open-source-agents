import React, { useState } from 'react';
import { ActionItem } from '../../shared/types.ts';
import { X, Calendar, Clock, AlertCircle } from 'lucide-react';

interface DeadlinePromptModalProps {
  task: ActionItem | null;
  isOpen: boolean;
  onClose: () => void;
  onSaveDeadline: (taskId: string, deadline: string) => void;
}

export const DeadlinePromptModal: React.FC<DeadlinePromptModalProps> = ({
  task,
  isOpen,
  onClose,
  onSaveDeadline,
}) => {
  const [selectedDate, setSelectedDate] = useState('');

  if (!isOpen || !task) return null;

  // Preset helpers
  const applyPreset = (preset: 'tomorrow' | 'endOfWeek' | 'nextWeek') => {
    const d = new Date();
    if (preset === 'tomorrow') {
      d.setDate(d.getDate() + 1);
      d.setHours(9, 0, 0, 0);
    } else if (preset === 'endOfWeek') {
      const day = d.getDay();
      const diff = 5 - day; // Friday
      d.setDate(d.getDate() + (diff > 0 ? diff : 7 + diff));
      d.setHours(17, 0, 0, 0);
    } else if (preset === 'nextWeek') {
      const day = d.getDay();
      const diff = 8 - (day === 0 ? 7 : day); // Next Monday
      d.setDate(d.getDate() + diff);
      d.setHours(9, 0, 0, 0);
    }

    // Format for datetime-local input (YYYY-MM-DDTHH:mm)
    const offset = d.getTimezoneOffset();
    const localTime = new Date(d.getTime() - offset * 60 * 1000);
    setSelectedDate(localTime.toISOString().slice(0, 16));
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDate) return;
    onSaveDeadline(task.id, new Date(selectedDate).toISOString());
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-amber-50/60">
          <div className="flex items-center gap-1.5 text-amber-800">
            <AlertCircle size={15} />
            <h3 className="text-xs font-bold">Action Item Deadline Needed</h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
          >
            <X size={15} />
          </button>
        </div>

        <div className="p-4 space-y-3.5 text-xs">
          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
              {task.owner}
            </span>
            <p className="text-xs font-medium text-slate-800 mt-0.5">{task.task}</p>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1.5 flex items-center gap-1">
              <Clock size={12} />
              Quick Presets
            </label>
            <div className="grid grid-cols-3 gap-1.5">
              <button
                type="button"
                onClick={() => applyPreset('tomorrow')}
                className="bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-2 rounded text-[10px] font-semibold transition-colors text-center"
              >
                Tomorrow 9 AM
              </button>
              <button
                type="button"
                onClick={() => applyPreset('endOfWeek')}
                className="bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-2 rounded text-[10px] font-semibold transition-colors text-center"
              >
                Fri 5 PM
              </button>
              <button
                type="button"
                onClick={() => applyPreset('nextWeek')}
                className="bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-2 rounded text-[10px] font-semibold transition-colors text-center"
              >
                Next Mon
              </button>
            </div>
          </div>

          <form onSubmit={handleSave} className="space-y-3">
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1 flex items-center gap-1">
                <Calendar size={12} />
                Specific Target Date & Time
              </label>
              <input
                type="datetime-local"
                required
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="w-full px-2.5 py-1.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs"
              />
            </div>

            <p className="text-[10px] text-slate-500">
              Setting this deadline will create a Google Calendar reminder with alerts at 24h & 2h prior, and dismiss pending email nudges.
            </p>

            <div className="pt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm"
              >
                Confirm & Sync
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

