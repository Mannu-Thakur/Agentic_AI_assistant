import React from 'react';
import { useResumeStore } from '../../store/resumeStore';
import { TemplateType } from '../../types/resume';

export const LivePreview: React.FC = () => {
  const { currentResume, selectedTemplate } = useResumeStore();
  const p = currentResume.personal;

  // Template styling classes
  const getTemplateStyles = (tpl: TemplateType) => {
    switch (tpl) {
      case 'classic_ats':
        return {
          container: 'bg-white text-gray-900 font-serif p-10 shadow-2xl max-w-[800px] mx-auto min-h-[1050px]',
          name: 'text-2xl font-bold uppercase tracking-wide text-black border-b-2 border-black pb-1',
          sectionHeader: 'text-sm font-bold uppercase border-b border-gray-400 pb-0.5 mt-4 mb-2 text-black',
          subhead: 'text-sm font-bold text-gray-900',
        };
      case 'minimal':
        return {
          container: 'bg-white text-gray-800 font-sans p-12 shadow-2xl max-w-[800px] mx-auto min-h-[1050px]',
          name: 'text-3xl font-light tracking-tight text-gray-900',
          sectionHeader: 'text-xs font-semibold tracking-widest uppercase text-gray-400 mt-6 mb-3',
          subhead: 'text-sm font-medium text-gray-900',
        };
      case 'executive':
        return {
          container: 'bg-slate-900 text-slate-100 font-sans p-10 shadow-2xl max-w-[800px] mx-auto min-h-[1050px]',
          name: 'text-3xl font-extrabold text-amber-400 tracking-tight',
          sectionHeader: 'text-xs font-bold uppercase tracking-wider text-amber-400/80 border-b border-amber-500/20 pb-1 mt-6 mb-3',
          subhead: 'text-sm font-bold text-white',
        };
      case 'developer':
        return {
          container: 'bg-zinc-950 text-zinc-200 font-mono p-8 shadow-2xl max-w-[800px] mx-auto min-h-[1050px] border border-zinc-800',
          name: 'text-2xl font-bold text-emerald-400',
          sectionHeader: 'text-xs font-bold text-emerald-500 border-b border-emerald-500/30 pb-1 mt-5 mb-2',
          subhead: 'text-sm font-bold text-zinc-100',
        };
      case 'academic':
        return {
          container: 'bg-amber-50/30 text-gray-900 font-serif p-12 shadow-2xl max-w-[800px] mx-auto min-h-[1050px]',
          name: 'text-2xl font-normal text-purple-950 border-b border-purple-900/30 pb-2',
          sectionHeader: 'text-xs font-bold uppercase tracking-widest text-purple-900 mt-6 mb-2',
          subhead: 'text-sm font-bold text-gray-900',
        };
      case 'modern':
      default:
        return {
          container: 'bg-white text-gray-900 font-sans p-10 shadow-2xl max-w-[800px] mx-auto min-h-[1050px] border border-gray-200',
          name: 'text-3xl font-extrabold text-violet-700 tracking-tight',
          sectionHeader: 'text-xs font-bold uppercase tracking-wider text-violet-700 border-b-2 border-violet-600 pb-1 mt-6 mb-3',
          subhead: 'text-sm font-bold text-gray-900',
        };
    }
  };

  const st = getTemplateStyles(selectedTemplate);

  return (
    <div className="p-6 overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar bg-card/20">
      <div className={st.container}>
        {/* Header */}
        <div className="space-y-1">
          <h1 className={st.name}>{p.name || 'Your Full Name'}</h1>
          {currentResume.headline && (
            <p className="text-xs text-indigo-600 font-medium">{currentResume.headline}</p>
          )}
          <div className="flex flex-wrap gap-2 text-[11px] text-gray-600 pt-1">
            {p.email && <span>{p.email}</span>}
            {p.phone && <span>• {p.phone}</span>}
            {p.location && <span>• {p.location}</span>}
            {p.linkedin && <span>• {p.linkedin.replace('https://', '')}</span>}
            {p.github && <span>• {p.github.replace('https://', '')}</span>}
          </div>
        </div>

        {/* Summary */}
        {currentResume.summary && (
          <div>
            <h2 className={st.sectionHeader}>Professional Summary</h2>
            <p className="text-xs leading-relaxed text-gray-700">{currentResume.summary}</p>
          </div>
        )}

        {/* Skills */}
        {currentResume.skills.length > 0 && (
          <div>
            <h2 className={st.sectionHeader}>Skills</h2>
            <div className="space-y-1 text-xs">
              {currentResume.skills.map((sg, idx) => (
                <div key={idx} className="flex space-x-2">
                  <span className="font-semibold text-gray-900 min-w-[120px]">{sg.category}:</span>
                  <span className="text-gray-700">{sg.skills.join(', ')}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Experience */}
        {currentResume.experience.length > 0 && (
          <div>
            <h2 className={st.sectionHeader}>Work Experience</h2>
            <div className="space-y-4">
              {currentResume.experience.map((exp, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between items-baseline">
                    <span className={st.subhead}>{exp.role} — <span className="font-semibold text-gray-700">{exp.company}</span></span>
                    <span className="text-[11px] text-gray-500 font-mono">{exp.start_date} – {exp.end_date || 'Present'}</span>
                  </div>
                  <ul className="list-disc list-inside text-xs text-gray-700 space-y-1">
                    {exp.bullets.map((b, bIdx) => (
                      <li key={bIdx} className="leading-relaxed">{b}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Projects */}
        {currentResume.projects.length > 0 && (
          <div>
            <h2 className={st.sectionHeader}>Projects</h2>
            <div className="space-y-3">
              {currentResume.projects.map((proj, idx) => (
                <div key={idx} className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="font-bold text-gray-900">{proj.name}</span>
                    {proj.technologies.length > 0 && (
                      <span className="text-[10px] text-violet-600">{proj.technologies.join(', ')}</span>
                    )}
                  </div>
                  {proj.description && <p className="text-gray-700">{proj.description}</p>}
                  <ul className="list-disc list-inside text-gray-700 space-y-0.5">
                    {proj.bullets.map((b, bIdx) => (
                      <li key={bIdx}>{b}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Education */}
        {currentResume.education.length > 0 && (
          <div>
            <h2 className={st.sectionHeader}>Education</h2>
            <div className="space-y-2">
              {currentResume.education.map((edu, idx) => (
                <div key={idx} className="flex justify-between items-baseline text-xs">
                  <div>
                    <span className="font-bold text-gray-900">{edu.institution}</span>
                    <span className="text-gray-700"> — {edu.degree} in {edu.field_of_study}</span>
                  </div>
                  <span className="text-[11px] text-gray-500 font-mono">{edu.start_date} – {edu.end_date}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
