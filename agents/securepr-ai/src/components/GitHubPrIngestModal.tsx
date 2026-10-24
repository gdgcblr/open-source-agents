import React, { useState } from 'react';
import { X, GitPullRequest, Upload, Key, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react';
import { PullRequestPreset } from '../types/security';

interface GitHubPrIngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPrLoaded: (preset: PullRequestPreset) => void;
}

export const GitHubPrIngestModal: React.FC<GitHubPrIngestModalProps> = ({
  isOpen,
  onClose,
  onPrLoaded,
}) => {
  const [prUrl, setPrUrl] = useState('');
  const [token, setToken] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ path: string; content: string }>>([]);

  if (!isOpen) return null;

  const handleFetchGitHubPr = async () => {
    if (!prUrl.trim()) return;
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/github/fetch-pr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prUrl: prUrl.trim(), token: token.trim() || undefined }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to fetch GitHub PR');
      }

      const newPreset: PullRequestPreset = {
        id: `gh-${data.prNumber}-${Date.now()}`,
        prNumber: data.prNumber,
        title: data.title,
        author: data.author,
        branch: data.branch,
        baseBranch: data.baseBranch,
        repo: data.repo,
        exposure: 'PUBLIC',
        description: data.description,
        files: data.files,
      };

      onPrLoaded(newPreset);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Error communicating with GitHub API');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    readFiles(files);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      readFiles(files);
    }
  };

  const readFiles = (fileList: File[]) => {
    const promises = fileList.map((file) => {
      return new Promise<{ path: string; content: string }>((resolve) => {
        const reader = new FileReader();
        reader.onload = (event) => {
          resolve({
            path: file.name,
            content: (event.target?.result as string) || '',
          });
        };
        reader.readAsText(file);
      });
    });

    Promise.all(promises).then((results) => {
      setUploadedFiles(results);
    });
  };

  const handleConfirmUpload = () => {
    if (uploadedFiles.length === 0) return;

    const newPreset: PullRequestPreset = {
      id: `upload-${Date.now()}`,
      prNumber: Math.floor(Math.random() * 900) + 100,
      title: `Uploaded PR: ${uploadedFiles.map((f) => f.path).join(', ').slice(0, 40)}`,
      author: 'developer',
      branch: 'upload-review',
      baseBranch: 'main',
      repo: 'user-uploads',
      exposure: 'PUBLIC',
      description: 'Custom repository code uploaded directly for security review and fix verification.',
      files: uploadedFiles.map((f) => ({
        path: f.path,
        status: 'modified',
        content: f.content,
        diff: f.content,
      })),
    };

    onPrLoaded(newPreset);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white border border-slate-200 rounded-xl max-w-xl w-full p-6 text-slate-800 shadow-2xl space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <GitPullRequest className="w-5 h-5 text-emerald-600" />
            <h3 className="text-base font-bold text-slate-900">
              Load GitHub PR or Upload Code
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Option 1: GitHub PR URL */}
        <div className="space-y-3">
          <label className="block text-xs font-bold text-slate-800">
            Option 1: Paste GitHub Pull Request Link
          </label>
          <div className="space-y-2">
            <input
              type="text"
              placeholder="https://github.com/owner/repository/pull/142"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-slate-400 focus:bg-white transition-colors"
            />
            <div className="flex items-center gap-2">
              <Key className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <input
                type="password"
                placeholder="GitHub Token (optional, for private repos or rate limit avoidance)"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:border-slate-400 font-mono"
              />
            </div>
          </div>

          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          <button
            onClick={handleFetchGitHubPr}
            disabled={!prUrl.trim() || isLoading}
            className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50 transition-colors flex items-center justify-center gap-2 shadow-xs"
          >
            {isLoading ? (
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <ArrowRight className="w-3.5 h-3.5" />
            )}
            <span>{isLoading ? 'Fetching PR from GitHub...' : 'Fetch & Review GitHub PR'}</span>
          </button>
        </div>

        <div className="relative flex py-1 items-center">
          <div className="flex-grow border-t border-slate-200"></div>
          <span className="flex-shrink mx-4 text-[10px] font-mono text-slate-400 uppercase font-semibold">
            OR
          </span>
          <div className="flex-grow border-t border-slate-200"></div>
        </div>

        {/* Option 2: Upload Files or Diff */}
        <div className="space-y-3">
          <label className="block text-xs font-bold text-slate-800">
            Option 2: Direct Repository / Diff File Upload
          </label>

          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            className="border-2 border-dashed border-slate-300 hover:border-slate-400 bg-slate-50/60 rounded-xl p-5 text-center cursor-pointer transition-colors"
          >
            <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
            <p className="text-xs text-slate-700 font-medium">
              Drag & drop code files (<code className="font-mono text-emerald-700 font-semibold">.diff, .patch, .py, .ts, .env</code>) here
            </p>
            <p className="text-[11px] text-slate-400 mt-1">
              or browse from your local file system
            </p>
            <input
              type="file"
              multiple
              onChange={handleFileInputChange}
              className="hidden"
              id="file-upload-input"
            />
            <label
              htmlFor="file-upload-input"
              className="mt-3 inline-block px-3 py-1.5 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-lg text-xs cursor-pointer font-semibold shadow-2xs"
            >
              Select Files
            </label>
          </div>

          {uploadedFiles.length > 0 && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1.5">
              <div className="font-bold text-slate-800 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>{uploadedFiles.length} files selected:</span>
              </div>
              <ul className="text-slate-600 font-mono text-[11px] pl-4 list-disc">
                {uploadedFiles.map((f, i) => (
                  <li key={i}>{f.path}</li>
                ))}
              </ul>
              <button
                onClick={handleConfirmUpload}
                className="w-full mt-2 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs"
              >
                Review Uploaded Code
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
