import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Search, Command, Zap, ChevronRight, Hash } from 'lucide-react';
import { cn } from '../../lib/utils';
import { aiService, SkillInfo } from '../../services/aiService';

export const CommandBar = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Toggle with CMD+K or Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 10);
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  // Fetch skills based on query
  useEffect(() => {
    if (query.length > 1) {
      aiService.searchSkills(query).then(setSkills).catch(() => setSkills([]));
    } else {
      setSkills([]);
    }
  }, [query]);

  const allResults = skills.map(s => ({ type: 'skill', ...s }));

  const handleSelect = useCallback((item: { type: string; id?: string }) => {
    if (item.type === 'skill') {
      console.log('Triggering skill:', item.id);
      // Extend here for real skill execution routing
    }
    setIsOpen(false);
  }, []);

  useEffect(() => {
    const handleNav = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % Math.max(allResults.length, 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + allResults.length) % Math.max(allResults.length, 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (allResults[selectedIndex]) {
          handleSelect(allResults[selectedIndex]);
        }
      }
    };
    window.addEventListener('keydown', handleNav);
    return () => window.removeEventListener('keydown', handleNav);
  }, [isOpen, selectedIndex, allResults, handleSelect]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={() => setIsOpen(false)} />
      
      <div className="relative w-full max-w-2xl bg-[#0a0a0a] border border-white/10 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="flex items-center px-4 py-4 border-b border-white/5">
          <Search className="text-zinc-500 mr-3" size={20} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search skills..."
            className="flex-1 bg-transparent border-none outline-none text-zinc-100 placeholder:text-zinc-600 text-lg"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-white/5 border border-white/10 text-[10px] text-zinc-400 font-mono">
            <Command size={10} /> K
          </div>
        </div>

        <div className="max-h-[60vh] overflow-y-auto py-2 custom-scrollbar">
          {allResults.length === 0 ? (
            <div className="px-4 py-8 text-center text-zinc-500 text-sm">
              {query.length > 1 ? `No skills found for "${query}"` : "Type to search skills"}
            </div>
          ) : (
            <div className="flex flex-col">
              {skills.length > 0 && (
                <Section title="Skills">
                  {skills.map((skill, i) => (
                    <Item
                      key={skill.id}
                      icon={<Zap size={16} className="text-amber-400" />}
                      label={skill.name}
                      description={skill.description}
                      selected={selectedIndex === i}
                      onClick={() => handleSelect({ type: 'skill', ...skill })}
                    />
                  ))}
                </Section>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-4 py-3 bg-white/[0.02] border-t border-white/5 text-[10px] text-zinc-500">
          <div className="flex gap-4">
            <span className="flex items-center gap-1"><ChevronRight size={10} /> Navigate</span>
            <span className="flex items-center gap-1"><Hash size={10} /> Select</span>
          </div>
          <span className="uppercase tracking-widest font-bold">Graxia Executive</span>
        </div>
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
};

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="mb-2">
    <div className="px-4 py-2 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{title}</div>
    {children}
  </div>
);

const Item = ({ icon, label, description, selected, onClick, badge }: {
  icon: React.ReactNode;
  label: string;
  description?: string;
  selected: boolean;
  onClick: () => void;
  badge?: string;
}) => (
  <div
    className={cn(
      "px-4 py-3 flex items-center gap-3 cursor-pointer transition-colors",
      selected ? "bg-white/5" : "hover:bg-white/[0.02]"
    )}
    onClick={onClick}
  >
    <div className="flex-shrink-0">{icon}</div>
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-zinc-100 truncate">{label}</span>
        {badge && (
          <span className="px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-tighter bg-zinc-800 text-zinc-400">
            {badge}
          </span>
        )}
      </div>
      {description && <div className="text-xs text-zinc-500 truncate">{description}</div>}
    </div>
    {selected && <div className="text-[10px] text-zinc-600 font-mono">Enter</div>}
  </div>
);
