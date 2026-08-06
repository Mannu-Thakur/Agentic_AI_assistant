import React, { useState, useRef } from 'react';
import { Upload, FileText, Sparkles, ArrowRight } from 'lucide-react';
import { useResumeStore, createEmptyResume } from '../../store/resumeStore';

export const UploadStep: React.FC = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const { uploadAndParseResume, isAnalyzingResume, setStep, setResumeData } = useResumeStore();

  const handleFile = async (file: File) => {
    if (!file) return;
    try {
      await uploadAndParseResume(file);
    } catch (err: any) {
      alert(err.message || 'Failed to parse resume');
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const startFromScratch = () => {
    setResumeData(createEmptyResume());
    setStep(2);
  };

  return (
    <div className="max-w-3xl mx-auto py-12 px-6 space-y-8 animate-in fade-in duration-300">
      {/* Title */}
      <div className="text-center space-y-3">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-400 text-xs font-semibold">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Step 1 of 3 — Upload Resume</span>
        </div>
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-violet-400 via-indigo-400 to-cyan-400">
          Upload Your Existing Resume
        </h1>
        <p className="text-muted-foreground text-sm max-w-xl mx-auto leading-relaxed">
          Upload your current PDF or DOCX resume. Our dual-layer OCR engine will parse it into structured JSON with 100% data fidelity.
        </p>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-3xl p-10 text-center cursor-pointer transition-all duration-300 ${
          dragActive
            ? 'border-violet-500 bg-violet-500/10 scale-[1.01]'
            : 'border-border hover:border-violet-500/50 hover:bg-card/40'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />

        {isAnalyzingResume ? (
          <div className="py-8 space-y-4 flex flex-col items-center">
            <div className="w-12 h-12 rounded-full border-4 border-violet-500 border-t-transparent animate-spin" />
            <div className="space-y-1">
              <h3 className="font-semibold text-lg">Parsing Resume with OCR & AI...</h3>
              <p className="text-xs text-muted-foreground">Extracting contact, skills, experience, and education</p>
            </div>
          </div>
        ) : (
          <div className="py-6 space-y-4 flex flex-col items-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-violet-600/20 to-indigo-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400 shadow-xl shadow-violet-900/10">
              <Upload className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h3 className="font-semibold text-lg">Drag & drop your resume file here</h3>
              <p className="text-xs text-muted-foreground">Supports PDF, DOCX, DOC, or TXT up to 15 MB</p>
            </div>
            <button
              type="button"
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium text-sm transition-all shadow-lg shadow-violet-600/25"
            >
              Browse Computer
            </button>
          </div>
        )}
      </div>

      {/* Alternative option */}
      <div className="flex items-center justify-between p-5 rounded-2xl border border-border bg-card/30">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-medium text-sm">Don't have a resume ready?</h4>
            <p className="text-xs text-muted-foreground">Start with an empty template and fill details manually</p>
          </div>
        </div>
        <button
          onClick={startFromScratch}
          className="flex items-center space-x-1.5 px-4 py-2 rounded-xl border border-border bg-secondary hover:bg-muted text-xs font-medium transition-all"
        >
          <span>Start Blank</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
