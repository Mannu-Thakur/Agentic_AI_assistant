import React, { useState, useEffect, useMemo } from 'react';
import {
  Code, Play, RefreshCw, Download, Copy, Check, ExternalLink,
  FileCode, Eye, AlertCircle, Zap, Layers
} from 'lucide-react';
import { useResumeStore } from '../../store/resumeStore';
import { resumeApi } from '../../services/resumeApi';
import { TemplateType } from '../../types/resume';

const DEFAULT_LATEX_SAMPLE = `\\documentclass[10pt,a4paper]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[margin=0.6in]{geometry}
\\usepackage{hyperref}
\\usepackage{titlesec}
\\usepackage{enumitem}
\\usepackage{xcolor}

\\definecolor{primary}{HTML}{2E40C7}
\\definecolor{accent}{HTML}{339EDC}
\\definecolor{darktext}{HTML}{1A1A1A}

\\hypersetup{colorlinks=true, linkcolor=primary, urlcolor=primary}
\\pagestyle{empty}
\\setlength{\\parindent}{0pt}
\\setlist[itemize]{leftmargin=*, noitemsep, topsep=2pt, parsep=1pt}

\\titleformat{\\section}{\\large\\bfseries\\color{primary}\\uppercase}{}{0em}{}[\\titlerule]
\\titlespacing*{\\section}{0pt}{10pt}{4pt}

\\begin{document}

\\begin{center}
{\\Huge \\bfseries \\color{primary} Alex Morgan}\\\\[4pt]
{\\large \\color{accent} \\textit{Senior Full Stack Engineer}} \\\\[6pt]
{\\small \\color{darktext} alex.morgan@email.com \\ \\$\\cdot\\$ \\ +1 (555) 019-2834 \\ \\$\\cdot\\$ \\ San Francisco, CA \\ \\$\\cdot\\$ \\ \\href{https://linkedin.com/in/alexmorgan}{linkedin.com/in/alexmorgan} \\ \\$\\cdot\\$ \\ \\href{https://github.com/alexmorgan}{github.com/alexmorgan}}
\\end{center}
\\vspace{-6pt}

\\section*{Professional Summary}
Innovative and results-driven Senior Software Engineer with 6+ years of experience designing scalable web applications, microservices architecture, and cloud infrastructure.

\\section*{Skills}
\\begin{itemize}[label={}]
  \\item \\textbf{Languages:} TypeScript, Python, JavaScript, Go, SQL, HTML/CSS
  \\item \\textbf{Frameworks \\& Libraries:} React.js, Next.js, FastAPI, Node.js, Express, TailwindCSS
  \\item \\textbf{Cloud \\& DevOps:} AWS, Docker, Kubernetes, CI/CD Pipelines, PostgreSQL, Redis
\\end{itemize}

\\section*{Work Experience}
\\noindent
\\textbf{Senior Full Stack Engineer} \\hfill {\\small \\color{darktext} 2022 -- Present}
\\\\
\\textit{TechCorp Systems}, San Francisco, CA
\\begin{itemize}
  \\item Architected real-time analytics dashboard serving over 500,000 active daily users with 99.99\\% uptime.
  \\item Reduced API latency by 45\\% through query optimization and Redis caching layer implementation.
  \\item Led a team of 5 engineers delivering high-impact features using Agile/Scrum methodologies.
\\end{itemize}

\\vspace{4pt}
\\noindent
\\textbf{Software Engineer} \\hfill {\\small \\color{darktext} 2019 -- 2022}
\\\\
\\textit{CloudScale Innovations}, Austin, TX
\\begin{itemize}
  \\item Developed microservices backend handling 10M+ daily events using Python FastAPI and PostgreSQL.
  \\item Created automated deployment pipelines reducing release deployment times from 2 hours to 10 minutes.
\\end{itemize}

\\section*{Projects}
\\noindent
\\textbf{AI-Powered Code Assistant} \\hfill {\\small \\color{accent} (React, Python, OpenAI, Docker)}
\\\\
Built an open-source IDE plugin enabling automated code refactoring and context-aware chat documentation.
\\begin{itemize}
  \\item Achieved 15,000+ GitHub stars and 50,000+ active extension downloads.
\\end{itemize}

\\section*{Education}
\\noindent
\\textbf{University of California, Berkeley} \\hfill {\\small \\color{darktext} 2015 -- 2019}
\\\\
\\textit{B.S. in Computer Science} (GPA: 3.85/4.0)

\\end{document}`;

export const LatexStudio: React.FC = () => {
  const { currentResume, setResumeData, selectedTemplate, setTemplate, recomputeATS } = useResumeStore();

  const [latexCode, setLatexCode] = useState<string>(DEFAULT_LATEX_SAMPLE);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isCompiling, setIsCompiling] = useState<boolean>(false);
  const [isParsing, setIsParsing] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [previewMode, setPreviewMode] = useState<'canvas' | 'pdf'>('canvas');
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string } | null>(null);

  // Auto-generate initial LaTeX code from current resume state if empty
  useEffect(() => {
    let isMounted = true;
    const fetchInitialLatex = async () => {
      setIsLoading(true);
      try {
        const res = await resumeApi.getLatexPreview({
          resume: currentResume,
          template: selectedTemplate,
        });
        if (isMounted && res.latex_code) {
          setLatexCode(res.latex_code);
        }
      } catch (err) {
        console.error('Failed to generate initial LaTeX code:', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchInitialLatex();
    return () => { isMounted = false; };
  }, [selectedTemplate]);

  // Sync from current Resume Store data
  const handleSyncFromResume = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await resumeApi.getLatexPreview({
        resume: currentResume,
        template: selectedTemplate,
      });
      setLatexCode(res.latex_code);
      setStatusMessage({ type: 'success', text: 'LaTeX code generated from current resume state!' });
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: `Failed to sync resume data: ${err.message}` });
    } finally {
      setIsLoading(false);
    }
  };

  // Parse custom pasted LaTeX back into structured Resume Store data
  const handleParseLatexToResume = async () => {
    if (!latexCode.trim()) return;
    setIsParsing(true);
    setStatusMessage(null);
    try {
      const res = await resumeApi.parseLatex(latexCode);
      if (res.resume) {
        setResumeData(res.resume);
        await recomputeATS();
        setStatusMessage({ type: 'success', text: 'Successfully parsed LaTeX code into structured resume & updated ATS score!' });
      }
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: `LaTeX Parsing Error: ${err.message}` });
    } finally {
      setIsParsing(false);
    }
  };

  // Compile LaTeX to PDF and trigger Download or PDF view
  const handleCompilePdf = async (downloadDirectly = false) => {
    if (!latexCode.trim()) return;
    setIsCompiling(true);
    setStatusMessage(null);
    try {
      const blob = await resumeApi.compileLatex({
        latex_code: latexCode,
        template: selectedTemplate,
      });
      const url = URL.createObjectURL(blob);
      setPdfBlobUrl(url);

      if (downloadDirectly) {
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(currentResume.personal.name || 'resume').toLowerCase().replace(/\s+/g, '_')}_latex.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setStatusMessage({ type: 'success', text: 'Compiled PDF downloaded successfully!' });
      } else {
        setPreviewMode('pdf');
        setStatusMessage({ type: 'success', text: 'PDF compiled successfully! Preview loaded below.' });
      }
    } catch (err: any) {
      setStatusMessage({ type: 'error', text: `PDF Compilation Error: ${err.message}` });
    } finally {
      setIsCompiling(false);
    }
  };

  // Download raw .tex file
  const handleDownloadTex = () => {
    const blob = new Blob([latexCode], { type: 'text/x-tex;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(currentResume.personal.name || 'resume').toLowerCase().replace(/\s+/g, '_')}.tex`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Copy LaTeX code to clipboard
  const handleCopyCode = () => {
    navigator.clipboard.writeText(latexCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Export to Overleaf
  const handleOpenOverleaf = () => {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = 'https://www.overleaf.com/docs';
    form.target = '_blank';

    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'snip';
    input.value = latexCode;

    form.appendChild(input);
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  };

  // Calculate lines for line-number column
  const lineNumbers = useMemo(() => {
    const count = latexCode.split('\n').length;
    return Array.from({ length: Math.max(count, 1) }, (_, i) => i + 1);
  }, [latexCode]);

  // Live High-Fidelity Canvas LaTeX Parser (Parses commands to visual DOM preview)
  const parsedCanvasView = useMemo(() => {
    if (!latexCode.trim()) return null;

    const cleanLatexText = (str: string): string => {
      if (!str) return '';
      return str
        // Remove LaTeX environments
        .replace(/\\begin\{[^}]*\}(\[[^\]]*\])?/g, '')
        .replace(/\\end\{[^}]*\}/g, '')
        
        // Remove styling tags but keep inner text
        .replace(/\\textbf\{([^}]+)\}/g, '$1')
        .replace(/\\textit\{([^}]+)\}/g, '$1')
        .replace(/\\emph\{([^}]+)\}/g, '$1')
        .replace(/\\underline\{([^}]+)\}/g, '$1')
        .replace(/\\href\{[^}]+\}\{([^}]+)\}/g, '$1')
        .replace(/\\color\{[^}]+\}\{([^}]+)\}/g, '$1')
        
        // Remove standalone macros
        .replace(/\\color\{[^}]+\}/g, '')
        .replace(/\\small\b/g, '')
        .replace(/\\large\b/g, '')
        .replace(/\\Large\b/g, '')
        .replace(/\\Huge\b/g, '')
        .replace(/\\bfseries\b/g, '')
        .replace(/\\itshape\b/g, '')
        .replace(/\\fa[A-Za-z0-9]+\s*/g, '')
        .replace(/\\textasciitilde\{\}/g, '~')
        .replace(/\\textasciicircum\{\}/g, '^')
        .replace(/\\vspace\{[^}]*\}/g, '')
        .replace(/\\hspace\{[^}]*\}/g, '')
        .replace(/\\hfill\s*\{?[^}]*\}?/g, '')
        .replace(/\\noindent/g, '')
        .replace(/\\titlerule/g, '')
        .replace(/\\\\/g, ' ')
        .replace(/\\item\s*/g, '')
        
        // Unescape TeX characters
        .replace(/\\_/g, '_')
        .replace(/\\&/g, '&')
        .replace(/\\%/g, '%')
        .replace(/\\#/g, '#')
        .replace(/\\\$/g, '$')
        .replace(/\\\{/g, '{')
        .replace(/\\\}/g, '}')
        .replace(/\\cdot/g, '•')
        .replace(/\\bullet/g, '•')
        
        .replace(/\s+/g, ' ')
        .trim();
    };

    // Extract Name
    let name = 'Your Name';
    const nameM = latexCode.match(/\\Huge\s+(?:\\bfseries\s+)?(?:\\color\{[^}]+\}\s+)?([^}\\\n]+)/i) ||
                  latexCode.match(/\\name\{([^}]+)\}/i);
    if (nameM) name = cleanLatexText(nameM[1]);

    // Extract Headline / Subtitle
    let headline = '';
    const headM = latexCode.match(/\\textit\{([^}]+)\}/i);
    if (headM && headM[1].length < 80) headline = cleanLatexText(headM[1]);

    // Extract Contacts
    const contacts: string[] = [];
    const hrefMatches = Array.from(latexCode.matchAll(/\\href\{([^}]+)\}\{([^}]+)\}/g));
    hrefMatches.forEach((m) => {
      const txt = cleanLatexText(m[2]);
      if (txt && !contacts.includes(txt)) contacts.push(txt);
    });

    const phoneM = latexCode.match(/\\faPhone\\\s*([^\s\\$]+)/i) || latexCode.match(/(\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}/);
    if (phoneM) {
      const pTxt = cleanLatexText(phoneM[1] || phoneM[0]);
      if (pTxt && !contacts.includes(pTxt)) contacts.push(pTxt);
    }

    const emailM = latexCode.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    if (emailM && !contacts.includes(emailM[0])) {
      contacts.unshift(emailM[0]);
    }

    // Extract Sections cleanly
    const sections: { title: string; items: string[]; textBlocks: { boldTitle: string; subtitle: string; date: string; bullets: string[] }[] }[] = [];
    const secSplits = latexCode.split(/\\section\*?\{([^}]+)\}/g);
    for (let i = 1; i < secSplits.length; i += 2) {
      const secTitle = cleanLatexText(secSplits[i]);
      const secRaw = secSplits[i + 1] || '';

      // Extract items/bullets from section
      const itemMatches = Array.from(secRaw.matchAll(/\\item\s+([^\n\\]+)/g));
      const items = itemMatches.map((m) => cleanLatexText(m[1])).filter(Boolean);

      // Extract structured entries like \textbf{Role/Company} ... \hfill {Date}
      const textBlocks: { boldTitle: string; subtitle: string; date: string; bullets: string[] }[] = [];
      const entrySplits = secRaw.split(/\\textbf\{([^}]+)\}/g);
      if (entrySplits.length > 1) {
        for (let j = 1; j < entrySplits.length; j += 2) {
          const boldTitle = cleanLatexText(entrySplits[j]);
          const blockBody = entrySplits[j + 1] || '';

          const dateM = blockBody.match(/\\hfill\s*\{?[^}]*?([A-Za-z0-9\s–\--]+)\}?/);
          const date = dateM ? cleanLatexText(dateM[1]) : '';

          const subM = blockBody.match(/\\textit\{([^}]+)\}/);
          const subtitle = subM ? cleanLatexText(subM[1]) : '';

          const bMatches = Array.from(blockBody.matchAll(/\\item\s+([^\n\\]+)/g));
          const bullets = bMatches.map((m) => cleanLatexText(m[1])).filter(Boolean);

          textBlocks.push({ boldTitle, subtitle, date, bullets });
        }
      }

      sections.push({ title: secTitle, items, textBlocks });
    }

    return (
      <div
        className="w-full shadow-2xl rounded-xl p-10 max-w-[820px] mx-auto min-h-[1050px] font-sans border border-zinc-300 transition-all"
        style={{ backgroundColor: '#ffffff', color: '#0f172a' }}
      >
        {/* Paper Header */}
        <div className="text-center pb-6 border-b-2 border-indigo-900/20 mb-6">
          <h1 className="text-3xl font-extrabold tracking-tight" style={{ color: '#1e3a8a' }}>{name}</h1>
          {headline && <p className="text-sm font-semibold italic mt-1" style={{ color: '#2563eb' }}>{headline}</p>}

          {contacts.length > 0 && (
            <div className="flex flex-wrap justify-center items-center gap-x-3 gap-y-1 mt-3 text-xs font-semibold" style={{ color: '#475569' }}>
              {contacts.map((c, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <span style={{ color: '#94a3b8' }}>•</span>}
                  <span>{c}</span>
                </React.Fragment>
              ))}
            </div>
          )}
        </div>

        {/* Paper Sections */}
        <div className="space-y-6">
          {sections.map((sec, idx) => (
            <div key={idx} className="space-y-3">
              <div className="border-b-2 border-indigo-900/30 pb-1">
                <h2 className="text-xs font-bold tracking-wider uppercase" style={{ color: '#1e3a8a' }}>{sec.title}</h2>
              </div>

              {/* Render Structured Text Blocks (Experience / Projects / Education) */}
              {sec.textBlocks.length > 0 ? (
                <div className="space-y-4">
                  {sec.textBlocks.map((tb, tbi) => (
                    <div key={tbi} className="space-y-1">
                      <div className="flex justify-between items-baseline text-xs font-bold" style={{ color: '#0f172a' }}>
                        <span>{tb.boldTitle}</span>
                        {tb.date && <span className="text-[11px] font-medium" style={{ color: '#64748b' }}>{tb.date}</span>}
                      </div>
                      {tb.subtitle && <div className="text-xs font-medium italic" style={{ color: '#334155' }}>{tb.subtitle}</div>}

                      {tb.bullets.length > 0 && (
                        <ul className="list-disc list-inside space-y-1 text-xs mt-1.5 pl-1" style={{ color: '#334155' }}>
                          {tb.bullets.map((b, bi) => (
                            <li key={bi} className="leading-relaxed">{b}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              ) : sec.items.length > 0 ? (
                /* Fallback List of Items */
                <ul className="list-disc list-inside space-y-1.5 text-xs pl-1" style={{ color: '#334155' }}>
                  {sec.items.map((it, iti) => (
                    <li key={iti} className="leading-relaxed">{it}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    );
  }, [latexCode]);

  return (
    <div className="w-full flex-1 min-h-[650px] flex flex-col bg-[#090a0f] text-zinc-100 overflow-hidden">
      {/* ── Top LaTeX Studio Toolbar ── */}
      <div className="border-b border-white/10 bg-zinc-900/90 px-6 py-3 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 px-3 py-1 rounded-xl bg-violet-600/20 border border-violet-500/30 text-violet-300 text-xs font-semibold">
            <Code className="w-4 h-4 text-violet-400" />
            <span>LaTeX Code Studio</span>
          </div>

          {/* Template Selector Preset */}
          <div className="flex items-center space-x-2 bg-zinc-800/80 px-2.5 py-1 rounded-xl border border-white/10 text-xs">
            <Layers className="w-3.5 h-3.5 text-zinc-400" />
            <span className="text-zinc-400 font-medium">Style:</span>
            <select
              value={selectedTemplate}
              onChange={(e) => setTemplate(e.target.value as TemplateType)}
              className="bg-transparent text-white font-semibold focus:outline-none cursor-pointer text-xs"
            >
              <option value="modern" className="bg-zinc-900">Modern Colorful</option>
              <option value="classic_ats" className="bg-zinc-900">Classic ATS Safe</option>
              <option value="minimal" className="bg-zinc-900">Minimal Clean</option>
              <option value="executive" className="bg-zinc-900">Executive C-Suite</option>
              <option value="developer" className="bg-zinc-900">Developer Monospace</option>
              <option value="academic" className="bg-zinc-900">Academic Citation</option>
            </select>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleSyncFromResume}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white text-xs font-medium transition-all"
            title="Generate LaTeX code from structured active resume state"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Sync from Resume</span>
          </button>

          <button
            onClick={handleParseLatexToResume}
            disabled={isParsing || !latexCode.trim()}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold shadow-md shadow-emerald-900/30 disabled:opacity-50 transition-all"
            title="Parse pasted LaTeX code into structured resume data for ATS scoring & AI editing"
          >
            {isParsing ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5" />
            )}
            <span>Parse to Resume</span>
          </button>

          <button
            onClick={() => handleCompilePdf(false)}
            disabled={isCompiling || !latexCode.trim()}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md shadow-violet-900/30 disabled:opacity-50 transition-all"
          >
            {isCompiling ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            <span>Compile Preview</span>
          </button>

          <button
            onClick={() => handleCompilePdf(true)}
            disabled={isCompiling || !latexCode.trim()}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-all shadow-sm"
          >
            <Download className="w-3.5 h-3.5" />
            <span>PDF</span>
          </button>

          <button
            onClick={handleDownloadTex}
            disabled={!latexCode.trim()}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white transition-all"
            title="Download .tex Source Code"
          >
            <FileCode className="w-4 h-4" />
          </button>

          <button
            onClick={handleCopyCode}
            disabled={!latexCode.trim()}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white transition-all"
            title="Copy LaTeX to Clipboard"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>

          <button
            onClick={handleOpenOverleaf}
            disabled={!latexCode.trim()}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 text-xs font-semibold transition-all"
            title="Open and edit directly in Overleaf"
          >
            <span>Overleaf</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Status Alert Banner */}
      {statusMessage && (
        <div
          className={`px-6 py-2 text-xs font-medium flex items-center justify-between border-b ${
            statusMessage.type === 'error'
              ? 'bg-rose-500/10 border-rose-500/20 text-rose-300'
              : statusMessage.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
              : 'bg-indigo-500/10 border-indigo-500/20 text-indigo-300'
          }`}
        >
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{statusMessage.text}</span>
          </div>
          <button
            onClick={() => setStatusMessage(null)}
            className="text-zinc-400 hover:text-white"
          >
            ×
          </button>
        </div>
      )}

      {/* ── Main Split View Editor & Preview ── */}
      <div className="flex-1 min-h-0 flex flex-col md:flex-row overflow-hidden">
        {/* Left Pane: Code Editor */}
        <div className="w-full md:w-1/2 h-1/2 md:h-full flex flex-col border-r border-white/10 bg-[#0c0e14]">
          <div className="px-4 py-2 bg-zinc-900/60 border-b border-white/5 flex items-center justify-between text-xs text-zinc-400">
            <div className="flex items-center space-x-2 font-mono text-[11px]">
              <span>LaTeX Code</span>
              <span className="text-zinc-600">|</span>
              <span>{lineNumbers.length} Lines</span>
              <span className="text-zinc-600">|</span>
              <span>{latexCode.length} Chars</span>
            </div>
            <button
              onClick={() => setLatexCode('')}
              className="text-zinc-500 hover:text-zinc-300 text-[11px]"
            >
              Clear Code
            </button>
          </div>

          <div className="flex-1 flex overflow-hidden font-mono text-xs relative">
            {/* Line numbers column */}
            <div className="w-12 bg-zinc-950/80 text-zinc-600 py-3 pr-2 text-right select-none border-r border-white/5 overflow-hidden shrink-0 font-mono text-[11px] leading-6">
              {lineNumbers.map((num) => (
                <div key={num}>{num}</div>
              ))}
            </div>

            {/* Monospace Code Editor Textarea */}
            <textarea
              value={latexCode}
              onChange={(e) => setLatexCode(e.target.value)}
              placeholder="Paste or type your LaTeX resume code here...\n\ne.g.,\n\documentclass[10pt,a4paper]{article}\n\begin{document}\n..."
              className="flex-1 bg-transparent text-zinc-200 p-3 leading-6 focus:outline-none resize-none custom-scrollbar font-mono text-xs border-none"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Right Pane: Live Document Render Preview */}
        <div className="w-full md:w-1/2 h-1/2 md:h-full flex flex-col bg-[#12141c]">
          <div className="px-4 py-2 bg-zinc-900/60 border-b border-white/5 flex items-center justify-between text-xs text-zinc-400">
            <div className="flex items-center space-x-2">
              <Eye className="w-3.5 h-3.5 text-violet-400" />
              <span className="font-semibold text-zinc-200">Live Formatted Preview</span>
            </div>

            <div className="flex items-center space-x-1 bg-zinc-950 p-1 rounded-lg border border-white/10 text-[11px]">
              <button
                onClick={() => setPreviewMode('canvas')}
                className={`px-2.5 py-0.5 rounded-md transition-all ${
                  previewMode === 'canvas' ? 'bg-violet-600 text-white font-semibold' : 'text-zinc-400 hover:text-white'
                }`}
              >
                Visual Canvas
              </button>
              <button
                onClick={() => {
                  setPreviewMode('pdf');
                  if (!pdfBlobUrl) handleCompilePdf(false);
                }}
                className={`px-2.5 py-0.5 rounded-md transition-all ${
                  previewMode === 'pdf' ? 'bg-violet-600 text-white font-semibold' : 'text-zinc-400 hover:text-white'
                }`}
              >
                PDF View
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar flex justify-center bg-[#090a0f]">
            {previewMode === 'canvas' ? (
              parsedCanvasView ? (
                parsedCanvasView
              ) : (
                <div className="flex flex-col items-center justify-center text-center p-12 text-zinc-500">
                  <FileCode className="w-12 h-12 mb-3 stroke-[1.5] text-zinc-600" />
                  <p className="text-sm font-medium">No LaTeX Code Provided</p>
                  <p className="text-xs text-zinc-600 mt-1 max-w-xs">
                    Paste LaTeX code on the left pane or click <b>Sync from Resume</b> to generate formatting.
                  </p>
                </div>
              )
            ) : pdfBlobUrl ? (
              <iframe
                src={pdfBlobUrl}
                className="w-full h-full rounded-xl border border-white/10 shadow-2xl bg-white min-h-[650px]"
                title="Compiled LaTeX PDF Preview"
              />
            ) : (
              <div className="flex flex-col items-center justify-center text-center p-12 text-zinc-500">
                <RefreshCw className="w-8 h-8 mb-3 animate-spin text-violet-400" />
                <p className="text-xs text-zinc-400">Compiling LaTeX PDF Document...</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
