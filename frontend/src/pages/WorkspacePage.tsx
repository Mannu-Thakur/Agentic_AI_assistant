import React, { useState, useEffect } from 'react';
import { apiRequest } from '../services/api';
import { useUIStore } from '../store/uiStore';
import { 
  FolderClosed, 
  Brain, 
  UploadCloud, 
  Trash2, 
  Plus, 
  CheckCircle2, 
  Loader2, 
  XCircle, 
  FileText,
  FileCode,
  Sparkles,
  Calendar,
  AlertCircle
} from 'lucide-react';

interface DocumentFile {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: 'processing' | 'ready' | 'failed';
  uploaded_at: string;
}

interface SemanticMemory {
  id: string;
  category: 'fact' | 'preference' | 'goal' | 'topic';
  content: string;
  importance_score: number;
  created_at: string;
}

export default function WorkspacePage() {
  const { activeView, setActiveView } = useUIStore();
  const [documents, setDocuments] = useState<DocumentFile[]>([]);
  const [memories, setMemories] = useState<SemanticMemory[]>([]);
  
  // Document state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  // Memory Form state
  const [memContent, setMemContent] = useState('');
  const [memCategory, setMemCategory] = useState<'fact' | 'preference' | 'goal' | 'topic'>('fact');
  const [memImportance, setMemImportance] = useState(5);
  const [memError, setMemError] = useState<string | null>(null);

  // Fetch data
  useEffect(() => {
    if (activeView === 'documents') {
      fetchDocuments();
    } else {
      fetchMemories();
    }
  }, [activeView]);

  const fetchDocuments = async () => {
    try {
      const data = await apiRequest('/documents');
      setDocuments(data);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  };

  const fetchMemories = async () => {
    try {
      const data = await apiRequest('/memories');
      setMemories(data);
    } catch (err) {
      console.error('Failed to load memories:', err);
    }
  };

  // Upload handler
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    setUploading(true);
    setUploadError(null);
    const file = files[0];
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      // Direct call because apiRequest doesn't support multipart/form-data natively due to JSON serialization checks
      const token = localStorage.getItem('access_token');
      const response = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        headers: {
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: formData
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'File upload failed');
      }
      
      await response.json();
      fetchDocuments();
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload document');
    } finally {
      setUploading(false);
    }
  };

  // Delete Document
  const handleDeleteDoc = async (id: string) => {
    try {
      await apiRequest(`/documents/${id}`, { method: 'DELETE' });
      setDocuments(documents.filter((doc) => doc.id !== id));
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  // Add Memory manual
  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memContent.trim()) return;
    
    setMemError(null);
    try {
      const newMemory = await apiRequest('/memories', {
        method: 'POST',
        json: {
          category: memCategory,
          content: memContent.trim(),
          importance_score: memImportance
        }
      });
      setMemories([newMemory, ...memories]);
      setMemContent('');
      setMemImportance(5);
    } catch (err: any) {
      setMemError(err.message || 'Failed to record memory');
    }
  };

  // Delete Memory
  const handleDeleteMemory = async (id: string) => {
    try {
      await apiRequest(`/memories/${id}`, { method: 'DELETE' });
      setMemories(memories.filter((m) => m.id !== id));
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Ingestion Hub</h1>
          <p className="text-muted-foreground text-xs mt-1">Manage documents and episodic memories injected into LLM contexts</p>
        </div>
        
        {/* Toggle tabs */}
        <div className="flex space-x-1 p-1 rounded-xl bg-secondary/50 border border-border self-start">
          <button
            onClick={() => setActiveView('documents')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeView === 'documents' 
                ? 'bg-card text-foreground shadow-sm' 
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <FolderClosed className="w-3.5 h-3.5" />
            <span>Documents</span>
          </button>
          <button
            onClick={() => setActiveView('memories')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeView === 'memories' 
                ? 'bg-card text-foreground shadow-sm' 
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Brain className="w-3.5 h-3.5" />
            <span>Semantic Memory</span>
          </button>
        </div>
      </div>

      {activeView === 'documents' ? (
        // Documents UI
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          
          {/* Upload card */}
          <div className="p-6 rounded-2xl border border-border bg-card/40 space-y-4 h-fit">
            <h3 className="text-sm font-semibold flex items-center space-x-2">
              <UploadCloud className="w-4.5 h-4.5 text-violet-400" />
              <span>Ingest Document</span>
            </h3>
            <p className="text-muted-foreground text-[10px] leading-relaxed">
              Upload PDF, TXT, DOCX, or Excel sheets. Our extraction pipeline automatically parses the file and writes vectorized indices into Chroma/FAISS.
            </p>
            
            <label className="w-full flex flex-col items-center justify-center border border-dashed border-border rounded-xl p-6 bg-secondary/15 hover:bg-secondary/35 cursor-pointer transition-all">
              {uploading ? (
                <>
                  <Loader2 className="w-6 h-6 animate-spin text-primary" />
                  <span className="text-[10px] font-medium mt-2">Parsing file content...</span>
                </>
              ) : (
                <>
                  <UploadCloud className="w-6 h-6 text-muted-foreground" />
                  <span className="text-[10px] font-semibold mt-2">Click to select files</span>
                  <span className="text-[9px] text-muted-foreground mt-0.5">PDF, DOCX, TXT up to 20MB</span>
                </>
              )}
              <input 
                type="file" 
                className="hidden" 
                onChange={handleFileUpload} 
                disabled={uploading} 
                accept=".pdf,.docx,.xlsx,.xls,.pptx,.txt" 
              />
            </label>
            
            {uploadError && (
              <div className="flex items-center space-x-1.5 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-[10px]">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}
          </div>

          {/* List documents */}
          <div className="md:col-span-2 space-y-4">
            <h3 className="text-sm font-semibold">Active Vector Store Files</h3>
            <div className="space-y-3">
              {documents.map((doc) => (
                <div key={doc.id} className="p-4 rounded-2xl border border-border bg-card/45 flex items-center justify-between shadow-sm">
                  <div className="flex items-center space-x-3.5 min-w-0">
                    <div className="p-2.5 rounded-xl bg-secondary/50 text-violet-400">
                      {doc.file_type.includes('code') ? <FileCode className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold truncate text-foreground">{doc.filename}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {(doc.size_bytes / 1024).toFixed(1)} KB &bull; Ingested {new Date(doc.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3.5">
                    {/* Status badge */}
                    <div className="flex items-center">
                      {doc.status === 'ready' && (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-green-500/10 text-green-400 border border-green-500/20">
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          <span>Vectorized</span>
                        </span>
                      )}
                      {doc.status === 'processing' && (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                          <span>Indexing</span>
                        </span>
                      )}
                      {doc.status === 'failed' && (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                          <XCircle className="w-2.5 h-2.5" />
                          <span>Failed</span>
                        </span>
                      )}
                    </div>
                    
                    <button 
                      onClick={() => handleDeleteDoc(doc.id)}
                      className="p-1.5 rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}

              {documents.length === 0 && (
                <div className="text-center py-16 border border-dashed border-border rounded-2xl bg-card/10 text-muted-foreground">
                  <FolderClosed className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
                  <p className="text-xs">No documents uploaded. Standard system queries will not execute RAG.</p>
                </div>
              )}
            </div>
          </div>

        </div>
      ) : (
        // Memories UI
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          
          {/* Add Memory Card */}
          <form onSubmit={handleAddMemory} className="p-6 rounded-2xl border border-border bg-card/40 space-y-4 h-fit">
            <h3 className="text-sm font-semibold flex items-center space-x-2">
              <Brain className="w-4.5 h-4.5 text-violet-400" />
              <span>Record Fact</span>
            </h3>
            
            <div className="space-y-1.5">
              <label className="text-[10px] font-semibold text-muted-foreground">Category</label>
              <select
                value={memCategory}
                onChange={(e) => setMemCategory(e.target.value as any)}
                className="w-full bg-secondary/40 border border-border rounded-xl py-2 px-3 text-xs focus:outline-none focus:border-primary text-foreground"
              >
                <option value="fact">Fact</option>
                <option value="preference">Preference</option>
                <option value="goal">Goal</option>
                <option value="topic">Topic</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-semibold text-muted-foreground">Fact Content</label>
              <textarea
                value={memContent}
                onChange={(e) => setMemContent(e.target.value)}
                placeholder="User prefers Python over JS for scripting..."
                rows={3}
                required
                className="w-full bg-secondary/40 border border-border rounded-xl py-2 px-3 text-xs focus:outline-none focus:border-primary text-foreground"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-[10px] font-semibold text-muted-foreground">
                <span>Importance Score</span>
                <span>{memImportance}/10</span>
              </div>
              <input
                type="range"
                min="1"
                max="10"
                value={memImportance}
                onChange={(e) => setMemImportance(Number(e.target.value))}
                className="w-full accent-primary h-1.5 bg-secondary rounded-lg appearance-none cursor-pointer"
              />
            </div>

            <button
              type="submit"
              className="w-full flex items-center justify-center space-x-2 py-2 rounded-xl bg-primary text-primary-foreground font-semibold text-xs transition-all hover:opacity-95 shadow-md shadow-primary/20"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Save Fact</span>
            </button>

            {memError && (
              <div className="flex items-center space-x-1.5 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-[10px]">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{memError}</span>
              </div>
            )}
          </form>

          {/* List memories */}
          <div className="md:col-span-2 space-y-4">
            <h3 className="text-sm font-semibold">Long-Term Epistemic Memory</h3>
            <div className="space-y-3">
              {memories.map((m) => (
                <div key={m.id} className="p-4 rounded-2xl border border-border bg-card/45 flex items-start justify-between shadow-sm">
                  <div className="space-y-1.5 min-w-0 pr-4">
                    <div className="flex items-center space-x-2.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[9px] font-semibold capitalize ${
                        m.category === 'preference' ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' :
                        m.category === 'goal' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        m.category === 'topic' ? 'bg-pink-500/10 text-pink-400 border border-pink-500/20' :
                        'bg-violet-500/10 text-violet-400 border border-violet-500/20'
                      }`}>
                        {m.category}
                      </span>
                      <span className="flex items-center space-x-1 text-[9px] text-muted-foreground font-medium">
                        <Sparkles className="w-3 h-3 text-yellow-400" />
                        <span>Importance: {m.importance_score}/10</span>
                      </span>
                    </div>
                    
                    <p className="text-xs leading-relaxed text-foreground">{m.content}</p>
                    
                    <p className="text-[9px] text-muted-foreground flex items-center space-x-1">
                      <Calendar className="w-3 h-3 text-muted-foreground" />
                      <span>Synthesized {new Date(m.created_at).toLocaleDateString()}</span>
                    </p>
                  </div>

                  <button 
                    onClick={() => handleDeleteMemory(m.id)}
                    className="p-1.5 rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all flex-shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}

              {memories.length === 0 && (
                <div className="text-center py-16 border border-dashed border-border rounded-2xl bg-card/10 text-muted-foreground">
                  <Brain className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
                  <p className="text-xs">No long-term memories extracted yet. Let the agent parse user context.</p>
                </div>
              )}
            </div>
          </div>

        </div>
      )}

    </div>
  );
}
