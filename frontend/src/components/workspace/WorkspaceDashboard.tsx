import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  FolderClosed, UploadCloud, Database, FileText, 
  Trash2, RefreshCw, Layers, ShieldCheck, HardDrive,
  FileCode, CheckCircle2
} from 'lucide-react';
import { apiRequest } from '../../services/api';

interface WorkspaceDoc {
  id: string;
  filename: string;
  size_bytes: number;
  created_at: string;
  status?: string;
  content_type?: string;
}

export function WorkspaceDashboard() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<WorkspaceDoc[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiRequest('/documents', { method: 'GET' });
      if (Array.isArray(res)) {
        setDocuments(res);
      } else if (res && Array.isArray(res.documents)) {
        setDocuments(res.documents);
      } else {
        setDocuments([]);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load workspace documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    try {
      await apiRequest('/documents/upload', {
        method: 'POST',
        body: formData,
      });
      await fetchDocuments();
    } catch (err: any) {
      setError(err?.message || 'Failed to upload document');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    try {
      await apiRequest(`/documents/${docId}`, { method: 'DELETE' });
      setDocuments(prev => prev.filter(d => d.id !== docId));
    } catch (err: any) {
      setError(err?.message || 'Failed to delete document');
    }
  };

  const totalSize = documents.reduce((acc, d) => acc + (d.size_bytes || 0), 0);
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };
  const formattedTotalSize = formatBytes(totalSize);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10 font-sans">
      {/* Header */}
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent flex items-center gap-3">
              <FolderClosed className="w-8 h-8 text-blue-400" />
              Workspace Knowledge Hub
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Manage your indexed documents, files, and vector retrieval context.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/settings?tab=documents')}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition border border-slate-700"
            >
              <Database className="w-4 h-4 text-purple-400" />
              RAG Settings
            </button>
            <label className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition cursor-pointer shadow-lg shadow-blue-500/20">
              <UploadCloud className="w-4 h-4" />
              {uploading ? 'Uploading...' : 'Upload Files'}
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.json,.csv,.png,.jpg,.jpeg,.bmp,.gif,.tiff,.webp,.heic,.heif"
                className="hidden"
                onChange={handleFileUpload}
                disabled={uploading}
              />
            </label>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="p-4 bg-red-950/60 border border-red-800 text-red-200 rounded-xl text-sm flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-xs underline text-red-300">
              Dismiss
            </button>
          </div>
        )}

        {/* Overview Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-5 bg-slate-900/60 border border-slate-800/80 rounded-2xl backdrop-blur-md">
            <div className="flex items-center justify-between text-slate-400 text-sm font-medium">
              <span>Indexed Documents</span>
              <FileText className="w-5 h-5 text-blue-400" />
            </div>
            <div className="text-3xl font-extrabold text-white mt-3">{documents.length}</div>
            <p className="text-xs text-slate-500 mt-1">Active files in vector store</p>
          </div>

          <div className="p-5 bg-slate-900/60 border border-slate-800/80 rounded-2xl backdrop-blur-md">
            <div className="flex items-center justify-between text-slate-400 text-sm font-medium">
              <span>Knowledge Storage</span>
              <HardDrive className="w-5 h-5 text-purple-400" />
            </div>
            <div className="text-3xl font-extrabold text-white mt-3">{formattedTotalSize}</div>
            <p className="text-xs text-slate-500 mt-1">Total vector index payload</p>
          </div>

          <div className="p-5 bg-slate-900/60 border border-slate-800/80 rounded-2xl backdrop-blur-md">
            <div className="flex items-center justify-between text-slate-400 text-sm font-medium">
              <span>RAG Protection</span>
              <ShieldCheck className={`w-5 h-5 ${documents.some(d => (d as any).status === 'processed' || (d as any).status === 'indexed' || (d as any).chunks_count > 0 || (d as any).chunk_count > 0) ? 'text-emerald-400' : (documents.length > 0 ? 'text-blue-400' : 'text-amber-400')}`} />
            </div>
            <div className={`text-3xl font-extrabold mt-3 ${documents.some(d => (d as any).status === 'processed' || (d as any).status === 'indexed' || (d as any).chunks_count > 0 || (d as any).chunk_count > 0) ? 'text-emerald-400' : (documents.length > 0 ? 'text-blue-400' : 'text-amber-400')}`}>
              {documents.some(d => (d as any).status === 'processed' || (d as any).status === 'indexed' || (d as any).chunks_count > 0 || (d as any).chunk_count > 0) ? 'Active' : (documents.length > 0 ? 'Ready' : 'Standby')}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {documents.some(d => (d as any).status === 'processed' || (d as any).status === 'indexed' || (d as any).chunks_count > 0 || (d as any).chunk_count > 0) ? 'Indexed vector retrieval context active' : (documents.length > 0 ? 'Documents loaded; vector embedding pending' : 'Upload documents to activate RAG context')}
            </p>
          </div>
        </div>

        {/* Document List */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden backdrop-blur-md">
          <div className="p-5 border-b border-slate-800/80 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
              <Layers className="w-5 h-5 text-blue-400" />
              Workspace Documents
            </h2>
            <button
              onClick={fetchDocuments}
              className="p-2 text-slate-400 hover:text-white rounded-lg transition hover:bg-slate-800"
              title="Refresh document list"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400 text-sm">
              Loading workspace documents...
            </div>
          ) : documents.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <FolderClosed className="w-12 h-12 text-slate-600 mx-auto" />
              <p className="text-slate-300 font-medium">No documents in this workspace yet</p>
              <p className="text-xs text-slate-500">Upload PDF, TXT, CSV, or Markdown files to enable RAG answers.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60">
              {documents.map(doc => (
                <div
                  key={doc.id}
                  className="p-4 sm:px-6 flex items-center justify-between hover:bg-slate-800/40 transition group"
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="p-2.5 bg-slate-800 rounded-xl text-blue-400 border border-slate-750">
                      <FileCode className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium text-slate-200 truncate group-hover:text-blue-300 transition">
                        {doc.filename}
                      </h3>
                      <div className="flex items-center gap-3 text-xs text-slate-400 mt-0.5">
                        <span>{(doc.size_bytes / 1024).toFixed(1)} KB</span>
                        <span>•</span>
                        <span>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Indexed'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 rounded-full">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Ready
                    </span>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-950/50 rounded-lg transition"
                      title="Delete document"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
