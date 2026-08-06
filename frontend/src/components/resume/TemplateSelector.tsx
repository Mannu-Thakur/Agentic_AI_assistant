import React from 'react';
import { Layout, Check } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';
import { TemplateType } from '../../types/resume';

const TEMPLATES: { id: TemplateType; name: string; desc: string; badge: string; color: string }[] = [
  { id: 'modern', name: 'Modern', desc: 'Clean gradient accent, 2-column skills, optimal for tech roles', badge: 'Popular', color: 'from-violet-500 to-indigo-500' },
  { id: 'classic_ats', name: 'Classic ATS', desc: '100% plain text, monochrome formatting, guarantees zero ATS parsing issues', badge: 'Safest', color: 'from-gray-600 to-slate-800' },
  { id: 'minimal', name: 'Minimal', desc: 'Generous whitespace, refined typography, minimalist executive feel', badge: 'Clean', color: 'from-emerald-500 to-teal-500' },
  { id: 'executive', name: 'Executive', desc: 'Dark theme header, bold accents, leadership & management focus', badge: 'Senior', color: 'from-amber-500 to-orange-500' },
  { id: 'developer', name: 'Developer', desc: 'Monospace code font accents, compact bullet structure', badge: 'Code', color: 'from-cyan-500 to-blue-500' },
  { id: 'academic', name: 'Academic', desc: 'Traditional serif typography, high information density', badge: 'Research', color: 'from-purple-500 to-pink-500' },
];

export const TemplateSelector: React.FC = () => {
  const { selectedTemplate, setTemplate } = useResumeStore();

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="space-y-1">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-foreground">
          <Layout className="w-5 h-5 text-violet-400" />
          <span>Resume PDF Template System</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Switch templates instantly. Content JSON remains identical — only visual typography and layout adapt.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {TEMPLATES.map((tpl) => {
          const isSelected = selectedTemplate === tpl.id;
          return (
            <div
              key={tpl.id}
              onClick={() => setTemplate(tpl.id)}
              className={`p-5 rounded-2xl border cursor-pointer transition-all duration-300 relative space-y-3 ${
                isSelected
                  ? 'border-violet-500 bg-violet-500/10 shadow-lg shadow-violet-500/10 scale-[1.02]'
                  : 'border-border bg-card/60 hover:border-violet-500/40 hover:bg-card'
              }`}
            >
              {isSelected && (
                <div className="absolute top-3 right-3 w-5 h-5 rounded-full bg-violet-500 text-white flex items-center justify-center">
                  <Check className="w-3.5 h-3.5" />
                </div>
              )}
              <div className={`w-8 h-8 rounded-xl bg-gradient-to-tr ${tpl.color} opacity-80`} />
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <h4 className="font-semibold text-sm text-foreground">{tpl.name}</h4>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-secondary text-muted-foreground font-medium">
                    {tpl.badge}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">{tpl.desc}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
