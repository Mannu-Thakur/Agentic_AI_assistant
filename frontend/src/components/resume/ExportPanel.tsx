import React, { useState } from 'react';
import { Download, FileText, Code, FileJson } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';
import { resumeApi } from '../../services/resumeApi';

export const ExportPanel: React.FC = () => {
  const { currentResume, selectedTemplate } = useResumeStore();
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleExport = async (format: 'pdf' | 'docx' | 'markdown' | 'json') => {
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
      link.setAttribute('download', `${nameSlug}_resume.${format === 'markdown' ? 'md' : format}`);
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

  const formats = [
    { id: 'pdf' as const, title: 'PDF Document', desc: 'Vector PDF with selected template layout & ATS safe typography', icon: FileText, badge: 'Recommended', color: 'from-violet-600 to-indigo-600' },
    { id: 'docx' as const, title: 'Microsoft Word (DOCX)', desc: 'Fully editable DOCX file for traditional recruiters', icon: FileText, badge: 'Editable', color: 'from-blue-600 to-cyan-600' },
    { id: 'markdown' as const, title: 'Markdown (.md)', desc: 'Clean GitHub markdown formatted resume', icon: Code, badge: 'Developer', color: 'from-emerald-600 to-teal-600' },
    { id: 'json' as const, title: 'Structured JSON (.json)', desc: 'Raw ResumeData schema for backup and API import', icon: FileJson, badge: 'Raw Data', color: 'from-amber-600 to-orange-600' },
  ];

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-foreground">
          <Download className="w-5 h-5 text-violet-400" />
          <span>Export Resume</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Download your tailored resume in multiple formats.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {formats.map((fmt) => {
          const IconComp = fmt.icon;
          const isDownloading = downloading === fmt.id;
          return (
            <div
              key={fmt.id}
              className="p-6 rounded-3xl border border-border bg-card/60 space-y-4 hover:border-violet-500/40 transition-all flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className={`w-10 h-10 rounded-2xl bg-gradient-to-tr ${fmt.color} flex items-center justify-center text-white shadow-lg`}>
                    <IconComp className="w-5 h-5" />
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] bg-secondary text-muted-foreground font-semibold">
                    {fmt.badge}
                  </span>
                </div>
                <div>
                  <h4 className="font-semibold text-base text-foreground">{fmt.title}</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed mt-1">{fmt.desc}</p>
                </div>
              </div>

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
            </div>
          );
        })}
      </div>
    </div>
  );
};
