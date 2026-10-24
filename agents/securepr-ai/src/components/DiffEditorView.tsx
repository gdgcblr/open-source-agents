import React, { useState } from 'react';
import { Play, FileCode, Plus } from 'lucide-react';

interface DiffEditorViewProps {
  files: Array<{ path: string; content: string; diff?: string; status?: string }>;
  onApplyAndScan: (files: Array<{ path: string; content: string; diff?: string }>) => void;
  isScanning: boolean;
}

export const DiffEditorView: React.FC<DiffEditorViewProps> = ({
  files: initialFiles,
  onApplyAndScan,
  isScanning,
}) => {
  const [editableFiles, setEditableFiles] = useState(initialFiles);
  const [activeFileIndex, setActiveFileIndex] = useState(0);
  const [showDiffMode, setShowDiffMode] = useState<'content' | 'diff'>('content');

  const activeFile = editableFiles[activeFileIndex] || editableFiles[0];

  const handleContentChange = (newContent: string) => {
    const updated = [...editableFiles];
    updated[activeFileIndex] = {
      ...updated[activeFileIndex],
      content: newContent,
    };
    setEditableFiles(updated);
  };

  const handleAddNewFile = () => {
    const newName = `src/routes/new_endpoint_${editableFiles.length + 1}.py`;
    const newFile = {
      path: newName,
      status: 'added',
      content: `from fastapi import FastAPI\n\napp = FastAPI()\n\n# New API endpoint\n@app.get("/api/v1/items/{item_id}")\ndef get_item(item_id: str):\n    return db.items.get(item_id)\n`,
      diff: `@@ -0,0 +1,7 @@\n+from fastapi import FastAPI\n+app = FastAPI()\n+@app.get("/api/v1/items/{item_id}")\n+def get_item(item_id: str):\n+    return db.items.get(item_id)`,
    };
    const updated = [...editableFiles, newFile];
    setEditableFiles(updated);
    setActiveFileIndex(updated.length - 1);
  };

  const handleInsertPayload = (type: string) => {
    if (!activeFile) return;
    let snippet = '';
    if (type === 'jwt_bypass') {
      snippet = `\n# Insecure JWT verification:\nclaims = jwt.decode(token, verify=False, algorithms=["none"])\n`;
    } else if (type === 'secret') {
      snippet = `\n# Exposed secret:\nAWS_SECRET_KEY = "AKIA1234567890ABCDEF"\nDATABASE_URL = "postgres://admin:SuperSecretPass!@db.internal:5432/db"\n`;
    } else if (type === 'bola') {
      snippet = `\n# BOLA endpoint:\n@app.post("/users/{user_id}/update")\ndef update_user(user_id: str, data: dict):\n    db.users.filter(id=user_id).update(**data)\n`;
    } else if (type === 'cors') {
      snippet = `\n# Permissive CORS:\napp.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)\n`;
    }

    handleContentChange(activeFile.content + snippet);
  };

  return (
    <div className="border border-slate-200 bg-white rounded-xl shadow-xs overflow-hidden flex flex-col h-[650px]">
      {/* Top Bar */}
      <div className="p-3.5 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileCode className="w-4 h-4 text-emerald-600" />
          <span className="text-xs font-bold text-slate-800">
            PR Code & Diff Workbench
          </span>
          <span className="text-xs text-slate-300">·</span>
          <span className="text-xs text-slate-500 font-medium">
            {editableFiles.length} files in change set
          </span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* Quick Payload Injectors for Testing */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-600">
            <span className="text-[11px] font-mono text-slate-400">Inject:</span>
            <button
              onClick={() => handleInsertPayload('jwt_bypass')}
              className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded text-[11px] font-mono shadow-2xs"
            >
              +JWT Bypass
            </button>
            <button
              onClick={() => handleInsertPayload('secret')}
              className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded text-[11px] font-mono shadow-2xs"
            >
              +AWS Key
            </button>
            <button
              onClick={() => handleInsertPayload('bola')}
              className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded text-[11px] font-mono shadow-2xs"
            >
              +BOLA Route
            </button>
            <button
              onClick={() => handleInsertPayload('cors')}
              className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded text-[11px] font-mono shadow-2xs"
            >
              +CORS Wildcard
            </button>
          </div>

          <button
            onClick={() => onApplyAndScan(editableFiles)}
            disabled={isScanning}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin' : ''}`} />
            <span>Re-scan Edited Code</span>
          </button>
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* File Tree / Tab List */}
        <div className="w-64 border-r border-slate-200 bg-slate-50/60 p-2 overflow-y-auto space-y-1">
          <div className="flex items-center justify-between px-2 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            <span>Files Changed</span>
            <button
              onClick={handleAddNewFile}
              className="hover:text-emerald-700 text-slate-400 p-0.5 rounded hover:bg-slate-100"
              title="Add file to scan"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          {editableFiles.map((file, idx) => (
            <button
              key={file.path}
              onClick={() => setActiveFileIndex(idx)}
              className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between font-mono transition-colors ${
                activeFileIndex === idx
                  ? 'bg-white text-emerald-800 font-bold border border-slate-200 shadow-2xs'
                  : 'text-slate-600 hover:bg-slate-100/80 hover:text-slate-900'
              }`}
            >
              <span className="truncate">{file.path}</span>
              <span
                className={`text-[10px] ml-1 shrink-0 font-bold ${
                  file.status === 'added'
                    ? 'text-emerald-700'
                    : file.status === 'deleted'
                    ? 'text-rose-700'
                    : 'text-amber-700'
                }`}
              >
                {file.status === 'added' ? '+A' : file.status === 'deleted' ? '-D' : '~M'}
              </span>
            </button>
          ))}
        </div>

        {/* Code Editor / Diff Inspector */}
        <div className="flex-1 flex flex-col bg-slate-900 overflow-hidden">
          {/* Subheader */}
          <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between text-xs bg-slate-950">
            <span className="font-mono text-slate-300 font-medium">
              {activeFile?.path}
            </span>

            <div className="flex items-center gap-2">
              <div className="flex items-center bg-slate-900 p-0.5 rounded border border-slate-800 text-[11px]">
                <button
                  onClick={() => setShowDiffMode('content')}
                  className={`px-2 py-0.5 rounded font-mono ${
                    showDiffMode === 'content'
                      ? 'bg-slate-800 text-slate-200 font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Editable Code
                </button>
                <button
                  onClick={() => setShowDiffMode('diff')}
                  className={`px-2 py-0.5 rounded font-mono ${
                    showDiffMode === 'diff'
                      ? 'bg-slate-800 text-slate-200 font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Unified Diff View
                </button>
              </div>
            </div>
          </div>

          {/* Editor Body */}
          <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-5">
            {showDiffMode === 'content' ? (
              <textarea
                value={activeFile?.content || ''}
                onChange={(e) => handleContentChange(e.target.value)}
                className="w-full h-full bg-transparent text-slate-200 resize-none focus:outline-none font-mono"
                spellCheck={false}
              />
            ) : (
              <pre className="text-slate-300 whitespace-pre font-mono">
                <code>
                  {(activeFile?.diff || activeFile?.content || '')
                    .split('\n')
                    .map((line, idx) => {
                      const isAdd = line.startsWith('+');
                      const isDel = line.startsWith('-');
                      const isHunk = line.startsWith('@@');

                      return (
                        <div
                          key={idx}
                          className={`${
                            isAdd
                              ? 'bg-emerald-950/40 text-emerald-300'
                              : isDel
                              ? 'bg-rose-950/40 text-rose-300'
                              : isHunk
                              ? 'text-cyan-400'
                              : 'text-slate-400'
                          }`}
                        >
                          {line}
                        </div>
                      );
                    })}
                </code>
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
