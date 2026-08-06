import React, { useState, useRef } from 'react';
import { Upload, ArrowRight } from 'lucide-react';
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
    <div className="flex-1 flex flex-col items-center justify-center py-12 px-6 max-w-2xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Title Hero */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
          Upload Your Existing Resume
        </h1>
        <p className="text-zinc-400 text-sm max-w-md mx-auto leading-relaxed">
          Upload your current PDF or DOCX resume to parse and tailor it with AI.
        </p>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`w-full glass-card-premium border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 flex flex-col items-center justify-center ${
          dragActive
            ? 'border-indigo-400 bg-indigo-500/10 scale-[1.005]'
            : 'border-zinc-700/60 hover:border-indigo-500/50 hover:bg-zinc-900/50'
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
          <div className="py-6 space-y-4 flex flex-col items-center">
            <div className="w-12 h-12 rounded-full border-3 border-indigo-500/30 border-t-indigo-400 animate-spin" />
            <div className="space-y-1 text-center">
              <h3 className="font-semibold text-base text-zinc-100">Parsing Resume with AI...</h3>
              <p className="text-xs text-zinc-400">Extracting contact info, skills, and work history</p>
            </div>
          </div>
        ) : (
          <div className="py-2 space-y-3 flex flex-col items-center">
            <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-md">
              <Upload className="w-7 h-7" />
            </div>

            <div className="space-y-1 text-center">
              <h3 className="font-semibold text-base text-zinc-100">
                Drag & drop your resume file here
              </h3>
              <p className="text-xs text-zinc-400">
                or <span className="text-indigo-400 font-medium hover:underline">click to browse</span> from your computer
              </p>
            </div>

            <p className="text-[11px] text-zinc-500 pt-2">
              Supports PDF, DOCX, DOC, or TXT up to 15 MB
            </p>
          </div>
        )}
      </div>

      {/* Secondary Options */}
      <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
        <button
          onClick={startFromScratch}
          className="inline-flex items-center space-x-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <span>Start with a blank template</span>
          <ArrowRight className="w-3.5 h-3.5 text-indigo-400" />
        </button>

        <span className="text-zinc-600 text-xs">•</span>

        <button
          onClick={() => {
            setResumeData(createEmptyResume());
            setStep(3);
            useResumeStore.getState().setActiveTab('latex');
          }}
          className="inline-flex items-center space-x-1.5 text-xs font-semibold text-violet-400 hover:text-violet-300 transition-colors"
        >
          <span>Use LaTeX Code Studio</span>
          <ArrowRight className="w-3.5 h-3.5 text-violet-400" />
        </button>
      </div>
    </div>
  );
};


