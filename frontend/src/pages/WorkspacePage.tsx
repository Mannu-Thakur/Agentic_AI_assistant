import React, { useState, useEffect, useRef } from 'react';
import { apiRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';
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
  AlertCircle,
  Info,
  ChevronRight,
  Database,
  Layers,
  Scissors,
  Cpu,
  HardDrive,
  Check,
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

// ── Ingestion pipeline steps ──────────────────────────────────
type IngestionStep = {
  id: string;
  icon: React.ElementType;
  label: string;
  detail: string;
};

const INGESTION_STEPS: IngestionStep[] = [
  { id: 'uploading',   icon: UploadCloud,   label: 'Uploading document',    detail: 'Transmitting file bytes to the server' },
  { id: 'parsing',     icon: FileText,      label: 'Parsing document',      detail: 'Extracting raw text from PDF/DOCX/XLSX' },
  { id: 'chunking',    icon: Scissors,      label: 'Chunking text',         detail: 'Splitting content into semantic segments' },
  { id: 'splitting',   icon: Layers,        label: 'Text splitting',         detail: 'Applying recursive character splitter' },
  { id: 'embedding',   icon: Cpu,           label: 'Creating embeddings',   detail: 'Encoding chunks into dense vector space' },
  { id: 'storing',     icon: HardDrive,     label: 'Storing in vector DB',  detail: 'Writing vectors into Chroma/FAISS index' },
  { id: 'indexing',    icon: Database,      label: 'Indexing complete',     detail: 'Document is ready for semantic retrieval' },
];

// ── Ingestion Progress component ─────────────────────────────
function IngestionProgress({
  filename,
  currentStep,
  done,
  error,
}: {
  filename: string;
  currentStep: number;
  done: boolean;
  error: string | null;
}) {
  return (
    <div className="mt-4 p-4 rounded-xl border border-accent/20 bg-accent/5 space-y-3">
      <div className="flex items-center gap-2">
        {done ? (
          <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
        ) : error ? (
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
        ) : (
          <Loader2 className="w-4 h-4 text-accent animate-spin flex-shrink-0" />
        )}
        <p className="text-xs font-semibold text-foreground truncate">
          {done ? 'Ingestion complete!' : error ? 'Ingestion failed' : `Processing: ${filename}`}
        </p>
      </div>

      {error && (
        <p className="text-[10px] text-red-400 bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-2 leading-relaxed">
          {error}
        </p>
      )}

      {!error && (
        <div className="space-y-1.5">
          {INGESTION_STEPS.map((step, idx) => {
            const StepIcon = step.icon;
            const isActive  = idx === currentStep && !done;
            const isDone    = done ? true : idx < currentStep;
            return (
              <div key={step.id} className="flex items-center gap-2.5">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300
                  ${isDone   ? 'bg-green-500/15 border border-green-500/30 text-green-400' :
                    isActive  ? 'bg-accent/15 border border-accent/30 text-accent step-active' :
                                'bg-surface-2 border border-border text-foreground-3 opacity-50'}`}>
                  {isDone
                    ? <Check className="w-2.5 h-2.5" />
                    : <StepIcon className="w-2.5 h-2.5" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[10px] font-semibold leading-none ${isDone ? 'text-green-400' : isActive ? 'text-accent' : 'text-foreground-3'}`}>
                    {step.label}
                  </p>
                  {isActive && (
                    <p className="text-[9px] text-foreground-3 mt-0.5 leading-normal">{step.detail}</p>
                  )}
                </div>
                {isActive && (
                  <div className="w-12 h-1 rounded-full bg-border overflow-hidden flex-shrink-0">
                    <div
                      className="h-full rounded-full animate-shimmer"
                      style={{
                        background: 'linear-gradient(90deg, hsl(var(--accent)/0.3) 0%, hsl(var(--accent)) 50%, hsl(var(--accent)/0.3) 100%)',
                        backgroundSize: '200% 100%',
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Pipeline explainer ────────────────────────────────────────
function PipelineExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-surface-2/50 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-surface-2 transition-colors"
      >
        <Info className="w-3.5 h-3.5 text-accent flex-shrink-0" />
        <span className="text-xs font-semibold text-foreground flex-1">How document ingestion works</span>
        <ChevronRight className={`w-3.5 h-3.5 text-foreground-3 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 animate-slide-up">
          <div className="h-px bg-border" />
          <p className="text-[11px] text-foreground-3 leading-relaxed">
            When you upload a document, Omni runs a multi-stage ingestion pipeline to make it searchable by the AI:
          </p>
          <div className="grid gap-2">
            {[
              { icon: FileText,  title: '1. Parse',      body: 'The raw file (PDF, DOCX, XLSX) is read and its text content is extracted by a specialised parser.' },
              { icon: Scissors,  title: '2. Chunk',      body: 'The extracted text is split into smaller, overlapping segments (chunks) using a recursive character-level splitter to preserve sentence context.' },
              { icon: Cpu,       title: '3. Embed',      body: 'Each chunk is passed through an embedding model (e.g. text-embedding-004) which converts it into a high-dimensional numerical vector that captures semantic meaning.' },
              { icon: Database,  title: '4. Index',      body: 'The vectors are stored in a local Chroma/FAISS vector database along with the original text. At query time, the AI retrieves the most semantically similar chunks and injects them as context.' },
            ].map(({ icon: Icon, title, body }) => (
              <div key={title} className="flex gap-2.5 p-2.5 rounded-lg bg-surface border border-border">
                <div className="w-6 h-6 rounded-md bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Icon className="w-3 h-3 text-accent" />
                </div>
                <div>
                  <p className="text-[10px] font-bold text-foreground">{title}</p>
                  <p className="text-[10px] text-foreground-3 leading-relaxed mt-0.5">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function WorkspacePage() {
  const { activeView, setActiveView } = useUIStore();
  const [documents, setDocuments] = useState<DocumentFile[]>([]);
  const [memories, setMemories] = useState<SemanticMemory[]>([]);
  
  // Document upload state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const token = useAuthStore((state) => state.token);
  const [ingestFilename, setIngestFilename] = useState<string>('');
  const [ingestStep, setIngestStep] = useState<number>(-1);      // -1 = idle
  const [ingestDone, setIngestDone] = useState(false);
  const ingestTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
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

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (ingestTimerRef.current) clearInterval(ingestTimerRef.current);
    };
  }, []);

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

  // Start the simulated ingestion progress animation
  const startIngestionProgress = (filename: string) => {
    setIngestFilename(filename);
    setIngestStep(0);
    setIngestDone(false);
    setUploadError(null);

    let step = 0;
    // Steps 0-5 auto-advance; step 6 (indexing complete) is set when we confirm backend is done
    const STEP_DURATIONS = [600, 900, 800, 700, 1200, 800]; // ms per step (0-5)

    const advance = () => {
      step += 1;
      setIngestStep(step);
      if (step < STEP_DURATIONS.length) {
        ingestTimerRef.current = setTimeout(advance, STEP_DURATIONS[step]) as any;
      }
      // step 6 = "Indexing complete" — will be set when poll confirms status=ready
    };

    ingestTimerRef.current = setTimeout(advance, STEP_DURATIONS[0]) as any;
  };

  // Poll the document list until the newly uploaded doc moves to 'ready'
  const pollUntilReady = async (docId: string) => {
    const MAX_POLLS = 30;
    let polls = 0;
    const interval = setInterval(async () => {
      polls++;
      try {
        const docs: DocumentFile[] = await apiRequest('/documents');
        setDocuments(docs);
        const doc = docs.find((d) => d.id === docId);
        if (doc && doc.status === 'ready') {
          clearInterval(interval);
          if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as any);
          setIngestStep(6); // "Indexing complete"
          setIngestDone(true);
          setUploading(false);
        } else if (doc && doc.status === 'failed') {
          clearInterval(interval);
          if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as any);
          setUploadError('Indexing failed on the server. Please try again.');
          setIngestStep(-1);
          setUploading(false);
        }
      } catch { /* ignore poll errors */ }
      if (polls >= MAX_POLLS) {
        clearInterval(interval);
        setIngestDone(true); // assume done after max polls
        setIngestStep(6);
        setUploading(false);
      }
    }, 2000);
  };

  // Upload handler
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    // Reset input value so same file can be re-selected
    e.target.value = '';
    setUploading(true);
    setUploadError(null);
    setIngestDone(false);
    setIngestStep(-1);

    const formData = new FormData();
    formData.append('file', file);

    try {
      startIngestionProgress(file.name);

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

      const doc: DocumentFile = await response.json();
      // Add to list immediately as 'processing'
      setDocuments((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)]);
      // Begin polling until status=ready
      pollUntilReady(doc.id);
    } catch (err: any) {
      if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as any);
      setUploadError(err.message || 'Failed to upload document');
      setIngestStep(-1);
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
        <div className="flex space-x-1 p-1 rounded-xl bg-surface-2 border border-border self-start">
          <button
            onClick={() => setActiveView('documents')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeView === 'documents' 
                ? 'bg-accent text-white shadow-sm shadow-accent/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-3'
            }`}
          >
            <FolderClosed className="w-3.5 h-3.5" />
            <span>Documents</span>
          </button>
          <button
            onClick={() => setActiveView('memories')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeView === 'memories' 
                ? 'bg-accent text-white shadow-sm shadow-accent/20' 
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-3'
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
          <div className="space-y-4">
            <div className="p-5 rounded-2xl border border-border bg-card/40 space-y-4">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <UploadCloud className="w-4 h-4 text-accent" />
                <span>Ingest Document</span>
              </h3>
              <p className="text-muted-foreground text-[10px] leading-relaxed">
                Upload PDF, TXT, DOCX, or Excel sheets. Omni parses, chunks, embeds, and indexes the content into the vector store automatically.
              </p>
              
              <label className={`w-full flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-6 cursor-pointer transition-all
                ${uploading
                  ? 'border-accent/40 bg-accent/5 cursor-not-allowed'
                  : 'border-border hover:border-accent/40 hover:bg-accent/5'}`}>
                <UploadCloud className={`w-7 h-7 mb-2 ${uploading ? 'text-accent' : 'text-foreground-3'}`} />
                <span className="text-[10px] font-semibold text-foreground">
                  {uploading ? 'Processing...' : 'Click to select a file'}
                </span>
                <span className="text-[9px] text-muted-foreground mt-1">PDF, DOCX, TXT, XLSX — up to 20 MB</span>
                <input 
                  type="file" 
                  className="hidden" 
                  onChange={handleFileUpload} 
                  disabled={uploading} 
                  accept=".pdf,.docx,.xlsx,.xls,.pptx,.txt,.md,.csv,.json" 
                />
              </label>

              {/* Ingestion progress */}
              {(ingestStep >= 0 || uploadError) && (
                <IngestionProgress
                  filename={ingestFilename}
                  currentStep={ingestStep}
                  done={ingestDone}
                  error={uploadError}
                />
              )}
            </div>

            {/* Pipeline explainer */}
            <PipelineExplainer />
          </div>

          {/* List documents */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Active Vector Store Files</h3>
              <span className="text-[10px] text-foreground-3 font-medium">{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="space-y-2.5">
              {documents.map((doc) => (
                <div key={doc.id} className="p-4 rounded-2xl border border-border bg-card/40 flex items-center justify-between shadow-sm hover:border-border-2 transition-colors">
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="p-2.5 rounded-xl bg-accent/10 border border-accent/20 text-accent flex-shrink-0">
                      {doc.file_type.includes('code') ? <FileCode className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold truncate text-foreground">{doc.filename}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {(doc.size_bytes / 1024).toFixed(1)} KB &bull; Ingested {new Date(doc.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 flex-shrink-0">
                    {doc.status === 'ready' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-green-500/10 text-green-400 border border-green-500/20">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                        Vectorized
                      </span>
                    )}
                    {doc.status === 'processing' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-accent/10 text-accent border border-accent/20">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                        Indexing
                      </span>
                    )}
                    {doc.status === 'failed' && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                        <XCircle className="w-2.5 h-2.5" />
                        Failed
                      </span>
                    )}
                    
                    <button 
                      onClick={() => handleDeleteDoc(doc.id)}
                      className="p-1.5 rounded-lg border border-border bg-surface-2 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 hover:border-red-500/20 transition-all"
                      title="Delete document"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}

              {documents.length === 0 && (
                <div className="text-center py-16 border-2 border-dashed border-border rounded-2xl bg-card/10 text-muted-foreground">
                  <FolderClosed className="w-8 h-8 mx-auto mb-3 text-foreground-3/40" />
                  <p className="text-xs font-medium">No documents uploaded yet</p>
                  <p className="text-[10px] mt-1 text-foreground-3">RAG will not activate until at least one document is indexed.</p>
                </div>
              )}
            </div>
          </div>

        </div>
      ) : (
        // Memories UI
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          
          {/* Add Memory Card */}
          <form onSubmit={handleAddMemory} className="p-5 rounded-2xl border border-border bg-card/40 space-y-4 h-fit">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Brain className="w-4 h-4 text-accent" />
              <span>Record Fact</span>
            </h3>
            
            <div className="space-y-1.5">
              <label className="text-[10px] font-semibold text-muted-foreground block">Category</label>
              <select
                value={memCategory}
                onChange={(e) => setMemCategory(e.target.value as any)}
                className="w-full rounded-xl py-2 px-3 text-xs focus:outline-none focus:ring-1 focus:ring-accent transition-all text-foreground"
                style={{
                  backgroundColor: 'hsl(var(--surface-2))',
                  border: '1px solid hsl(var(--border-2))',
                  color: 'hsl(var(--foreground))',
                }}
              >
                <option value="fact">Fact</option>
                <option value="preference">Preference</option>
                <option value="goal">Goal</option>
                <option value="topic">Topic</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-semibold text-muted-foreground block">Fact Content</label>
              <textarea
                value={memContent}
                onChange={(e) => setMemContent(e.target.value)}
                placeholder="User prefers Python over JS for scripting..."
                rows={3}
                required
                className="w-full rounded-xl py-2 px-3 text-xs focus:outline-none focus:ring-1 focus:ring-accent transition-all resize-none text-foreground"
                style={{
                  backgroundColor: 'hsl(var(--surface-2))',
                  border: '1px solid hsl(var(--border-2))',
                  color: 'hsl(var(--foreground))',
                }}
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-[10px] font-semibold text-muted-foreground">
                <span>Importance Score</span>
                <span className="text-accent">{memImportance}/10</span>
              </div>
              <input
                type="range"
                min="1"
                max="10"
                value={memImportance}
                onChange={(e) => setMemImportance(Number(e.target.value))}
                className="w-full h-1.5 rounded-lg appearance-none cursor-pointer"
                style={{ accentColor: 'hsl(var(--accent))' }}
              />
            </div>

            <button
              type="submit"
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-accent text-white font-semibold text-xs transition-all hover:opacity-90 shadow-md shadow-accent/20"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Save Fact</span>
            </button>

            {memError && (
              <div className="flex items-center gap-1.5 p-3 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-[10px]">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{memError}</span>
              </div>
            )}
          </form>

          {/* List memories */}
          <div className="md:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Long-Term Epistemic Memory</h3>
              <span className="text-[10px] text-foreground-3 font-medium">{memories.length} entr{memories.length !== 1 ? 'ies' : 'y'}</span>
            </div>
            <div className="space-y-2.5">
              {memories.map((m) => (
                <div key={m.id} className="p-4 rounded-2xl border border-border bg-card/40 flex items-start justify-between shadow-sm hover:border-border-2 transition-colors">
                  <div className="space-y-1.5 min-w-0 pr-4">
                    <div className="flex items-center gap-2.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[9px] font-semibold capitalize ${
                        m.category === 'preference' ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' :
                        m.category === 'goal'       ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        m.category === 'topic'      ? 'bg-pink-500/10 text-pink-400 border border-pink-500/20' :
                        'bg-accent/10 text-accent border border-accent/20'
                      }`}>
                        {m.category}
                      </span>
                      <span className="flex items-center gap-1 text-[9px] text-muted-foreground font-medium">
                        <Sparkles className="w-3 h-3 text-yellow-400" />
                        <span>Importance: {m.importance_score}/10</span>
                      </span>
                    </div>
                    
                    <p className="text-xs leading-relaxed text-foreground">{m.content}</p>
                    
                    <p className="text-[9px] text-muted-foreground flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      <span>Synthesized {new Date(m.created_at).toLocaleDateString()}</span>
                    </p>
                  </div>

                  <button 
                    onClick={() => handleDeleteMemory(m.id)}
                    className="p-1.5 rounded-lg border border-border bg-surface-2 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 hover:border-red-500/20 transition-all flex-shrink-0"
                    title="Delete memory"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}

              {memories.length === 0 && (
                <div className="text-center py-16 border-2 border-dashed border-border rounded-2xl bg-card/10 text-muted-foreground">
                  <Brain className="w-8 h-8 mx-auto mb-3 text-foreground-3/40" />
                  <p className="text-xs font-medium">No long-term memories yet</p>
                  <p className="text-[10px] mt-1 text-foreground-3">Let the agent parse user context to auto-extract facts.</p>
                </div>
              )}
            </div>
          </div>

        </div>
      )}

    </div>
  );
}
