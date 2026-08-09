import React, { useState, useEffect } from 'react';
import { Download, FileText, Code, FileJson, Copy, Check, Eye, FileCode } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';
import { resumeApi } from '../../services/resumeApi';
import { ExportFormat } from '../../types/resume';

export const ExportPanel: React.FC = () => {
  const { currentResume, selectedTemplate } = useResumeStore();
  const [downloading, setDownloading] = useState<string | null>(null);

  // LaTeX Preview & Copy states
  const [latexCode, setLatexCode] = useState<string>('');
  const [loadingLatex, setLoadingLatex] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [showLatexViewer, setShowLatexViewer] = useState<boolean>(false);

  // Fetch LaTeX Preview lazily — only when the viewer panel is open
  useEffect(() => {
    if (!showLatexViewer) return;
    let isMounted = true;
    const fetchLatex = async () => {
      setLoadingLatex(true);
      try {
        const res = await resumeApi.getLatexPreview({
          resume: currentResume,
          template: selectedTemplate,
        });
        if (isMounted) {
          setLatexCode(res.latex_code);
        }
      } catch (err) {
        console.error('Failed to load LaTeX preview:', err);
      } finally {
        if (isMounted) setLoadingLatex(false);
      }
    };
    fetchLatex();
    return () => { isMounted = false; };
  }, [showLatexViewer, currentResume, selectedTemplate]);

  const handleExport = async (format: ExportFormat) => {
    setDownloading(format);
    try {
      const blob = await resumeApi.downloadExport({
        resume: currentResume,
        format,
        template: selectedTemplate,
      });

      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const nameSlug = (currentResume.personal.name || 'resume').toLowerCase().replace(/\s+/g, '_');
      const ext = format === 'markdown' ? 'md' : format === 'latex' ? 'tex' : format;
      link.setAttribute('download', `${nameSlug}_resume.${ext}`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err.message || `Failed to export ${format.toUpperCase()}`);
    } finally {
      setDownloading(null);
    }
  };

  const handleCopyLatex = async () => {
    if (!latexCode) return;
    try {
      await navigator.clipboard.writeText(latexCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (err) {
      console.error('Failed to copy to clipboard', err);
    }
  };

  const formats = [
    { id: 'pdf' as const, title: 'PDF Document', desc: 'Vector PDF with selected template layout & ATS safe typography', icon: FileText, badge: 'Recommended', color: 'from-violet-600 to-indigo-600' },
    { id: 'latex' as const, title: 'LaTeX Code (.tex)', desc: 'Compilation-ready LaTeX source for Overleaf, XeLaTeX & pdfLaTeX', icon: FileCode, badge: 'Academic / Overleaf', color: 'from-fuchsia-600 to-pink-600' },
    { id: 'docx' as const, title: 'Microsoft Word (DOCX)', desc: 'Fully editable DOCX file for traditional recruiters', icon: FileText, badge: 'Editable', color: 'from-blue-600 to-cyan-600' },
    { id: 'markdown' as const, title: 'Markdown (.md)', desc: 'Clean GitHub markdown formatted resume', icon: Code, badge: 'Developer', color: 'from-emerald-600 to-teal-600' },
    { id: 'json' as const, title: 'Structured JSON (.json)', desc: 'Raw ResumeData schema for backup and API import', icon: FileJson, badge: 'Raw Data', color: 'from-amber-600 to-orange-600' },
  ];

  return (
    <div className="space-y-8 p-6 max-w-5xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-foreground">
          <Download className="w-5 h-5 text-violet-400" />
          <span>Export Resume</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Download or copy your tailored resume in PDF, LaTeX (.tex), DOCX, Markdown, or JSON formats.
        </p>
      </div>

      {/* Export Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {formats.map((fmt) => {
          const IconComp = fmt.icon;
          const isDownloading = downloading === fmt.id;
          return (
            <div
              key={fmt.id}
              className="p-5 rounded-3xl border border-border bg-card/60 space-y-4 hover:border-violet-500/40 transition-all flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className={`w-9 h-9 rounded-2xl bg-gradient-to-tr ${fmt.color} flex items-center justify-center text-white shadow-lg`}>
                    <IconComp className="w-4 h-4" />
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] bg-secondary text-muted-foreground font-semibold">
                    {fmt.badge}
                  </span>
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-foreground">{fmt.title}</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed mt-1">{fmt.desc}</p>
                </div>
              </div>

              <div className="space-y-2">
                <button
                  onClick={() => handleExport(fmt.id)}
                  disabled={!!downloading}
                  className="flex items-center justify-center space-x-2 w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-violet-600/20 disabled:opacity-50 transition-all"
                >
                  {isDownloading ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Generating {fmt.id.toUpperCase()}...</span>
                    </>
                  ) : (
                    <>
                      <Download className="w-3.5 h-3.5" />
                      <span>Download {fmt.id.toUpperCase()}</span>
                    </>
                  )}
                </button>

                {fmt.id === 'latex' && (
                  <button
                    onClick={() => setShowLatexViewer(!showLatexViewer)}
                    className="flex items-center justify-center space-x-1.5 w-full py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-muted-foreground hover:text-foreground text-[11px] font-medium border border-border transition-all"
                  >
                    <Eye className="w-3 h-3 text-fuchsia-400" />
                    <span>{showLatexViewer ? 'Hide LaTeX Viewer' : 'View LaTeX Code'}</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Interactive LaTeX Code Viewer Panel */}
      {showLatexViewer && (
        <div className="border border-fuchsia-500/30 rounded-3xl bg-zinc-950/90 overflow-hidden shadow-2xl space-y-0">
          <div className="bg-zinc-900/90 border-b border-white/10 px-5 py-3.5 flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-lg bg-fuchsia-600/20 border border-fuchsia-500/30 flex items-center justify-center text-fuchsia-400">
                <FileCode className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-zinc-100 flex items-center space-x-2">
                  <span>LaTeX Source Code Viewer</span>
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-mono bg-fuchsia-500/10 text-fuchsia-300 border border-fuchsia-500/20 uppercase">
                    Template: {selectedTemplate}
                  </span>
                </h4>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  Copy this code to paste directly into Overleaf, or download the .tex file to compile locally with XeLaTeX or pdfLaTeX.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={handleCopyLatex}
                disabled={loadingLatex || !latexCode}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-fuchsia-600 hover:bg-fuchsia-500 text-white text-xs font-semibold shadow-md shadow-fuchsia-600/25 transition-all disabled:opacity-50"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-300" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Code</span>
                  </>
                )}
              </button>

              <button
                onClick={() => handleExport('latex')}
                disabled={!!downloading}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-zinc-200 text-xs font-semibold transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download .tex</span>
              </button>
            </div>
          </div>

          <div className="p-4 bg-zinc-950/80 relative">
            {loadingLatex ? (
              <div className="py-12 flex flex-col items-center justify-center space-y-2 text-zinc-400 text-xs">
                <div className="w-6 h-6 border-2 border-fuchsia-500 border-t-transparent rounded-full animate-spin" />
                <span>Generating LaTeX source code...</span>
              </div>
            ) : (
              <pre className="text-[11px] font-mono text-zinc-300 leading-relaxed max-h-[380px] overflow-y-auto custom-scrollbar p-4 bg-zinc-900/60 rounded-xl border border-white/5 select-all whitespace-pre-wrap break-words">
                <code>{latexCode}</code>
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
