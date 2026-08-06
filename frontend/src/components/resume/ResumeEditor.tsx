import React from 'react';
import { User, Briefcase, Code, Globe, Plus, Trash2 } from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';

export const ResumeEditor: React.FC = () => {
  const { currentResume, updateResume } = useResumeStore();

  const updatePersonal = (field: string, val: string) => {
    updateResume((prev) => ({
      ...prev,
      personal: { ...prev.personal, [field]: val },
    }));
  };

  // ── Experience helpers ──
  const updateExperience = (index: number, field: string, val: any) => {
    updateResume((prev) => {
      const exp = [...prev.experience];
      exp[index] = { ...exp[index], [field]: val };
      return { ...prev, experience: exp };
    });
  };

  const addExperience = () => {
    updateResume((prev) => ({
      ...prev,
      experience: [
        ...prev.experience,
        {
          id: `exp_${Date.now()}`,
          company: 'Company Name',
          role: 'Job Title',
          location: 'City, Country',
          start_date: 'Jan 2023',
          end_date: 'Present',
          is_current: true,
          bullets: ['Key achievement or responsibility...'],
          technologies: [],
        },
      ],
    }));
  };

  const removeExperience = (index: number) => {
    updateResume((prev) => ({
      ...prev,
      experience: prev.experience.filter((_, i) => i !== index),
    }));
  };

  const updateBullet = (expIndex: number, bulletIndex: number, val: string) => {
    updateResume((prev) => {
      const exp = [...prev.experience];
      const bullets = [...exp[expIndex].bullets];
      bullets[bulletIndex] = val;
      exp[expIndex] = { ...exp[expIndex], bullets };
      return { ...prev, experience: exp };
    });
  };

  const addBullet = (expIndex: number) => {
    updateResume((prev) => {
      const exp = [...prev.experience];
      exp[expIndex] = {
        ...exp[expIndex],
        bullets: [...exp[expIndex].bullets, 'New measurable achievement...'],
      };
      return { ...prev, experience: exp };
    });
  };

  const removeBullet = (expIndex: number, bulletIndex: number) => {
    updateResume((prev) => {
      const exp = [...prev.experience];
      exp[expIndex] = {
        ...exp[expIndex],
        bullets: exp[expIndex].bullets.filter((_, i) => i !== bulletIndex),
      };
      return { ...prev, experience: exp };
    });
  };

  // ── Skills helpers ──
  const updateSkillCategory = (catIndex: number, val: string) => {
    updateResume((prev) => {
      const skills = [...prev.skills];
      skills[catIndex] = { ...skills[catIndex], category: val };
      return { ...prev, skills };
    });
  };

  const updateSkillList = (catIndex: number, val: string) => {
    const list = val.split(',').map((s) => s.trim()).filter(Boolean);
    updateResume((prev) => {
      const skills = [...prev.skills];
      skills[catIndex] = { ...skills[catIndex], skills: list };
      return { ...prev, skills };
    });
  };

  const addSkillGroup = () => {
    updateResume((prev) => ({
      ...prev,
      skills: [...prev.skills, { category: 'Tools & Frameworks', skills: ['Docker', 'Git'] }],
    }));
  };

  const removeSkillGroup = (catIndex: number) => {
    updateResume((prev) => ({
      ...prev,
      skills: prev.skills.filter((_, i) => i !== catIndex),
    }));
  };

  return (
    <div className="space-y-8 p-6 max-w-4xl mx-auto overflow-y-auto max-h-[calc(100vh-140px)] custom-scrollbar">
      {/* Personal Information */}
      <div className="p-6 rounded-2xl border border-border bg-card/60 space-y-4">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-violet-400">
          <User className="w-5 h-5" />
          <span>Personal Information</span>
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="block text-muted-foreground mb-1">Full Name</label>
            <input
              type="text"
              value={currentResume.personal.name}
              onChange={(e) => updatePersonal('name', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Email</label>
            <input
              type="email"
              value={currentResume.personal.email}
              onChange={(e) => updatePersonal('email', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Phone</label>
            <input
              type="text"
              value={currentResume.personal.phone}
              onChange={(e) => updatePersonal('phone', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Location</label>
            <input
              type="text"
              value={currentResume.personal.location}
              onChange={(e) => updatePersonal('location', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">LinkedIn URL</label>
            <input
              type="text"
              value={currentResume.personal.linkedin}
              onChange={(e) => updatePersonal('linkedin', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">GitHub URL</label>
            <input
              type="text"
              value={currentResume.personal.github}
              onChange={(e) => updatePersonal('github', e.target.value)}
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="p-6 rounded-2xl border border-border bg-card/60 space-y-4">
        <h3 className="font-semibold text-lg flex items-center space-x-2 text-indigo-400">
          <Globe className="w-5 h-5" />
          <span>Professional Summary</span>
        </h3>
        <textarea
          rows={4}
          value={currentResume.summary}
          onChange={(e) => updateResume((prev) => ({ ...prev, summary: e.target.value }))}
          className="w-full p-3 rounded-xl border border-border bg-background text-xs leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-violet-500"
        />
      </div>

      {/* Skills */}
      <div className="p-6 rounded-2xl border border-border bg-card/60 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-lg flex items-center space-x-2 text-cyan-400">
            <Code className="w-5 h-5" />
            <span>Skills</span>
          </h3>
          <button
            onClick={addSkillGroup}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-border bg-secondary hover:bg-muted text-xs transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Category</span>
          </button>
        </div>

        {currentResume.skills.map((sg, idx) => (
          <div key={idx} className="p-4 rounded-xl border border-border bg-background/50 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <input
                type="text"
                value={sg.category}
                onChange={(e) => updateSkillCategory(idx, e.target.value)}
                placeholder="Category (e.g. Languages)"
                className="font-semibold p-1.5 rounded-lg border border-border bg-background text-foreground"
              />
              <button
                onClick={() => removeSkillGroup(idx)}
                className="p-1 rounded text-red-400 hover:bg-red-500/10"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              value={sg.skills.join(', ')}
              onChange={(e) => updateSkillList(idx, e.target.value)}
              placeholder="Comma-separated skills (e.g. Python, React, Docker)"
              className="w-full p-2.5 rounded-xl border border-border bg-background text-foreground"
            />
          </div>
        ))}
      </div>

      {/* Experience */}
      <div className="p-6 rounded-2xl border border-border bg-card/60 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-lg flex items-center space-x-2 text-emerald-400">
            <Briefcase className="w-5 h-5" />
            <span>Work Experience</span>
          </h3>
          <button
            onClick={addExperience}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-border bg-secondary hover:bg-muted text-xs transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Position</span>
          </button>
        </div>

        {currentResume.experience.map((exp, expIdx) => (
          <div key={exp.id || expIdx} className="p-5 rounded-2xl border border-border bg-background/50 space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm text-foreground">Position #{expIdx + 1}</span>
              <button
                onClick={() => removeExperience(expIdx)}
                className="p-1 rounded text-red-400 hover:bg-red-500/10"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-muted-foreground mb-1">Company</label>
                <input
                  type="text"
                  value={exp.company}
                  onChange={(e) => updateExperience(expIdx, 'company', e.target.value)}
                  className="w-full p-2 rounded-lg border border-border bg-background text-foreground"
                />
              </div>
              <div>
                <label className="block text-muted-foreground mb-1">Role Title</label>
                <input
                  type="text"
                  value={exp.role}
                  onChange={(e) => updateExperience(expIdx, 'role', e.target.value)}
                  className="w-full p-2 rounded-lg border border-border bg-background text-foreground"
                />
              </div>
              <div>
                <label className="block text-muted-foreground mb-1">Start Date</label>
                <input
                  type="text"
                  value={exp.start_date}
                  onChange={(e) => updateExperience(expIdx, 'start_date', e.target.value)}
                  className="w-full p-2 rounded-lg border border-border bg-background text-foreground"
                />
              </div>
              <div>
                <label className="block text-muted-foreground mb-1">End Date</label>
                <input
                  type="text"
                  value={exp.end_date}
                  onChange={(e) => updateExperience(expIdx, 'end_date', e.target.value)}
                  className="w-full p-2 rounded-lg border border-border bg-background text-foreground"
                />
              </div>
            </div>

            {/* Bullets */}
            <div className="space-y-2">
              <label className="block font-medium text-muted-foreground">Bullet Points</label>
              {exp.bullets.map((b, bIdx) => (
                <div key={bIdx} className="flex items-center space-x-2">
                  <textarea
                    rows={2}
                    value={b}
                    onChange={(e) => updateBullet(expIdx, bIdx, e.target.value)}
                    className="flex-1 p-2 rounded-lg border border-border bg-background text-foreground resize-y"
                  />
                  <button
                    onClick={() => removeBullet(expIdx, bIdx)}
                    className="p-1 rounded text-red-400 hover:bg-red-500/10"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              <button
                onClick={() => addBullet(expIdx)}
                className="text-xs text-violet-400 hover:underline flex items-center space-x-1 pt-1"
              >
                <Plus className="w-3 h-3" />
                <span>Add Bullet</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
