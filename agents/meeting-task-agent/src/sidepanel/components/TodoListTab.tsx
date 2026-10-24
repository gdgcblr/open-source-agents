import React, { useState } from 'react';
import { ActionItem } from '../../shared/types.ts';
import {
  CheckCircle2,
  Circle,
  Calendar,
  AlertTriangle,
  Clock,
  Plus,
  ExternalLink,
  XCircle,
  Sparkles,
} from 'lucide-react';

interface TodoListTabProps {
  tasks: ActionItem[];
  onUpdateTask: (taskId: string, updates: Partial<ActionItem>) => void;
  onExtractActions: () => void;
  onOpenAddTask: () => void;
  onPromptDeadline: (task: ActionItem) => void;
  isExtracting: boolean;
  transcriptCount: number;
}

export const TodoListTab: React.FC<TodoListTabProps> = ({
  tasks,
  onUpdateTask,
  onExtractActions,
  onOpenAddTask,
  onPromptDeadline,
  isExtracting,
  transcriptCount,
}) => {
  const [selectedOwner, setSelectedOwner] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'completed'>('all');

  // Extract unique owners for filter pills
  const owners = Array.from(new Set(tasks.map((t) => t.owner))).filter(Boolean);

  const filteredTasks = tasks.filter((task) => {
    const matchesOwner = selectedOwner === 'all' || task.owner === selectedOwner;
    const matchesStatus =
      filterStatus === 'all'
        ? task.status !== 'cancelled'
        : task.status === filterStatus;
    return matchesOwner && matchesStatus;
  });

  const missingDeadlineTasks = tasks.filter((t) => t.status === 'pending' && !t.deadline);
  const pendingTasks = tasks.filter((t) => t.status === 'pending');
  const completedTasks = tasks.filter((t) => t.status === 'completed');

  return (
    <div className="space-y-4">
      {/* Top Action Bar */}
      <div className="flex items-center gap-2">
        <button
          onClick={onExtractActions}
          disabled={isExtracting || transcriptCount === 0}
          className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-semibold px-3 py-2 rounded-lg shadow-sm transition-all flex items-center justify-center gap-1.5"
        >
          <Sparkles size={13} className={isExtracting ? 'animate-spin' : ''} />
          {isExtracting ? 'Extracting with Gemma...' : 'Extract Action Items'}
        </button>

        <button
          onClick={onOpenAddTask}
          className="bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold px-3 py-2 rounded-lg shadow-sm transition-all flex items-center gap-1 shrink-0"
        >
          <Plus size={14} />
          Add Task
        </button>
      </div>

      {/* Warning Card for Missing Deadlines (Feature 4) */}
      {missingDeadlineTasks.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2.5 shadow-2xs">
          <AlertTriangle size={16} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="text-xs flex-1">
            <span className="font-bold text-amber-900">
              {missingDeadlineTasks.length} task{missingDeadlineTasks.length > 1 ? 's' : ''} missing a deadline
            </span>
            <p className="text-amber-800 text-[11px] mt-0.5 leading-snug">
              The agent requires a deadline to schedule Calendar reminders and will send an email nudge if unset.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {missingDeadlineTasks.slice(0, 3).map((item) => (
                <button
                  key={item.id}
                  onClick={() => onPromptDeadline(item)}
                  className="bg-white hover:bg-amber-100 text-amber-900 border border-amber-300 rounded px-2 py-0.5 text-[10px] font-semibold flex items-center gap-1 transition-colors"
                >
                  <Clock size={10} />
                  Set date for {item.owner}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filter Tabs: By Owner & Status */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-medium text-slate-500">
          <div className="flex items-center gap-1">
            <span>Pending ({pendingTasks.length})</span>
            <span>•</span>
            <span>Done ({completedTasks.length})</span>
          </div>
          <div className="flex gap-1 bg-slate-100 p-0.5 rounded-lg text-[11px]">
            <button
              onClick={() => setFilterStatus('all')}
              className={`px-2 py-0.5 rounded ${filterStatus === 'all' ? 'bg-white font-semibold text-slate-800 shadow-2xs' : 'text-slate-500'}`}
            >
              All
            </button>
            <button
              onClick={() => setFilterStatus('pending')}
              className={`px-2 py-0.5 rounded ${filterStatus === 'pending' ? 'bg-white font-semibold text-slate-800 shadow-2xs' : 'text-slate-500'}`}
            >
              Pending
            </button>
            <button
              onClick={() => setFilterStatus('completed')}
              className={`px-2 py-0.5 rounded ${filterStatus === 'completed' ? 'bg-white font-semibold text-slate-800 shadow-2xs' : 'text-slate-500'}`}
            >
              Done
            </button>
          </div>
        </div>

        {/* Owner Pills */}
        {owners.length > 1 && (
          <div className="flex items-center gap-1 overflow-x-auto pb-1 text-xs">
            <button
              onClick={() => setSelectedOwner('all')}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition-colors ${
                selectedOwner === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              All Owners ({tasks.length})
            </button>
            {owners.map((owner) => {
              const count = tasks.filter((t) => t.owner === owner).length;
              return (
                <button
                  key={owner}
                  onClick={() => setSelectedOwner(owner)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition-colors ${
                    selectedOwner === owner
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {owner} ({count})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Task List */}
      <div className="space-y-2.5">
        {filteredTasks.length === 0 ? (
          <div className="bg-white rounded-xl p-8 border border-dashed border-slate-300 text-center">
            <CheckCircle2 size={24} className="mx-auto text-slate-300 mb-2" />
            <h4 className="text-xs font-semibold text-slate-700">No tasks to display</h4>
            <p className="text-[11px] text-slate-500 mt-1">
              Extract action items from the meeting transcript or add a custom task.
            </p>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isCompleted = task.status === 'completed';
            const isCancelled = task.status === 'cancelled';

            return (
              <div
                key={task.id}
                className={`bg-white rounded-xl p-3 border transition-all shadow-xs ${
                  isCompleted
                    ? 'border-emerald-100 bg-emerald-50/20'
                    : isCancelled
                    ? 'border-slate-200 opacity-60'
                    : 'border-slate-200/90 hover:border-blue-300'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  {/* Tick off checkbox (Feature 5) */}
                  <button
                    onClick={() =>
                      onUpdateTask(task.id, {
                        status: isCompleted ? 'pending' : 'completed',
                      })
                    }
                    className="mt-0.5 text-slate-400 hover:text-blue-600 transition-colors shrink-0"
                    title={isCompleted ? 'Mark as incomplete' : 'Mark as completed'}
                  >
                    {isCompleted ? (
                      <CheckCircle2 size={18} className="text-emerald-500 fill-emerald-50" />
                    ) : (
                      <Circle size={18} />
                    )}
                  </button>

                  <div className="flex-1 min-w-0">
                    {/* Task Title & Owner */}
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="font-semibold text-xs text-blue-900 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-100">
                        {task.owner}
                      </span>
                      <span className="text-[10px] text-slate-400 truncate max-w-[110px]" title={task.meetingTitle}>
                        {task.meetingTitle}
                      </span>
                    </div>

                    <p
                      className={`text-xs text-slate-800 leading-snug font-normal ${
                        isCompleted ? 'line-through text-slate-400' : ''
                      }`}
                    >
                      {task.task}
                    </p>

                    {/* Metadata: Deadline, Calendar link, Reschedule */}
                    <div className="mt-2.5 flex items-center justify-between pt-2 border-t border-slate-100 text-[11px]">
                      {task.deadline ? (
                        <button
                          onClick={() => onPromptDeadline(task)}
                          className="flex items-center gap-1 text-slate-600 hover:text-blue-600 font-medium transition-colors"
                          title="Click to reschedule"
                        >
                          <Calendar size={12} className="text-slate-400" />
                          <span>{new Date(task.deadline).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => onPromptDeadline(task)}
                          className="flex items-center gap-1 text-amber-700 bg-amber-50 hover:bg-amber-100 px-1.5 py-0.5 rounded font-semibold transition-colors"
                        >
                          <AlertTriangle size={11} />
                          Set Deadline
                        </button>
                      )}

                      <div className="flex items-center gap-2">
                        {task.calendarEventUrl && (
                          <a
                            href={task.calendarEventUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="text-blue-600 hover:text-blue-800 flex items-center gap-0.5"
                            title="Open in Google Calendar"
                          >
                            <Calendar size={12} />
                            <ExternalLink size={9} />
                          </a>
                        )}

                        <button
                          onClick={() => onUpdateTask(task.id, { status: 'cancelled' })}
                          className="text-slate-400 hover:text-red-500 transition-colors"
                          title="Cancel task"
                        >
                          <XCircle size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

