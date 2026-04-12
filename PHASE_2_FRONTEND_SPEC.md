# Phase 2: Frontend Redesign — Complete Specification
**Claude Code Dark + Mission Control HUD (A+C Design)**

---

## OVERVIEW

### Goals
1. ✓ Redesign 13 pages with A+C design system
2. ✓ Implement 40+ component library (Storybook)
3. ✓ Real-time WebSocket integration for agent streams
4. ✓ Dark mode as default + light mode toggle
5. ✓ Lighthouse 90+ all metrics
6. ✓ WCAG 2.1 AA accessibility
7. ✓ Component test coverage 80%+

### Timeline
4-6 weeks (parallel with Phase 1 Tasks 41-56)

### Tech Stack
- **Framework:** React 18 + TypeScript
- **Build:** Vite + Bun
- **Styling:** Tailwind CSS 3.x
- **State:** React Query (server) + Zustand (client)
- **Real-Time:** WebSocket + JSON
- **Testing:** Vitest + React Testing Library
- **Docs:** Storybook + Chromatic

---

## DESIGN SYSTEM

### Color Palette

#### Dark Mode (Primary)
```css
/* Base Colors */
--color-bg-primary: #0d1117;         /* Page background */
--color-bg-secondary: #161b22;       /* Elevated surfaces (cards) */
--color-bg-tertiary: #21262d;        /* Hover state */
--color-border: #30363d;             /* Dividers */
--color-border-light: #444c56;       /* Lighter dividers */
--color-text-primary: #e6edf3;       /* Main text */
--color-text-secondary: #8b949e;     /* Secondary text */
--color-text-tertiary: #6e7681;      /* Disabled text */

/* Accent Colors */
--color-accent-green: #3fb950;       /* Success, active */
--color-accent-blue: #58a6ff;        /* Info, interactive */
--color-accent-orange: #f0883e;      /* Warning */
--color-accent-red: #da3633;         /* Error, danger */
--color-accent-cyan: #00d4ff;        /* HUD highlights */
--color-accent-lime: #00ff9d;        /* Mission Control highlight */
--color-accent-purple: #79c0ff;      /* Alternative highlight */

/* Semantic Colors */
--color-success: #3fb950;
--color-warning: #f0883e;
--color-error: #da3633;
--color-info: #58a6ff;
--color-disabled: #6e7681;

/* Gradients */
--gradient-brand: linear-gradient(135deg, #00d4ff, #00ff9d);
--gradient-danger: linear-gradient(135deg, #da3633, #f0883e);
```

#### Light Mode (Secondary)
```css
--color-bg-primary: #ffffff;
--color-bg-secondary: #f6f8fa;
--color-bg-tertiary: #eaeef2;
--color-border: #d0d7de;
--color-border-light: #e1e4e8;
--color-text-primary: #24292f;
--color-text-secondary: #57606a;
--color-text-tertiary: #6e7681;
/* Keep accent colors same for consistency */
```

### Typography

```css
/* Font Family Stack */
--font-family-base: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
--font-family-mono: 'Menlo', 'Monaco', 'Courier New', 'JetBrains Mono', 'Fira Code', monospace;

/* Font Sizes */
--font-size-xs: 12px;    /* Small labels, badges */
--font-size-sm: 14px;    /* Secondary text, small UI */
--font-size-base: 16px;  /* Body text */
--font-size-lg: 18px;    /* Secondary headings (h3) */
--font-size-xl: 20px;    /* Primary headings (h2) */
--font-size-2xl: 28px;   /* Page title (h1) */

/* Font Weights */
--font-weight-regular: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;

/* Line Heights */
--line-height-tight: 1.25;
--line-height-normal: 1.5;
--line-height-relaxed: 1.75;
```

### Spacing System

```
4px, 8px, 12px, 16px, 24px, 32px, 48px, 64px

Usage:
--spacing-xs: 4px       /* Tight spacing, borders */
--spacing-sm: 8px       /* Component padding */
--spacing-md: 12px      /* Standard padding */
--spacing-lg: 16px      /* Card padding, margins */
--spacing-xl: 24px      /* Section padding */
--spacing-2xl: 32px     /* Major spacing */
--spacing-3xl: 48px     /* Page padding */
--spacing-4xl: 64px     /* Large whitespace */
```

### Transitions & Animations

```css
/* Durations */
--duration-fast: 150ms;     /* Hover states, small changes */
--duration-medium: 300ms;   /* Modal opens, page transitions */
--duration-slow: 500ms;     /* Loading states, major transitions */

/* Easing */
--ease-in: cubic-bezier(0.4, 0, 1, 1);
--ease-out: cubic-bezier(0, 0, 0.2, 1);
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

/* Common Transitions */
transition: all 150ms ease-in-out;
transition: background-color 150ms, color 150ms;
transition: transform 300ms ease-out;
```

### Shadows

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.2);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.3);
--shadow-2xl: 0 25px 50px rgba(0, 0, 0, 0.4);
```

### Borders & Radius

```css
--radius-sm: 4px;       /* Small components, subtle */
--radius-md: 6px;       /* Standard radius */
--radius-lg: 8px;       /* Cards, larger components */
--radius-xl: 12px;      /* Modals, panels */

--border-width-thin: 1px;
--border-width-normal: 2px;
```

---

## COMPONENT LIBRARY (40+ Components)

### Base Components

#### 1. Button
```typescript
// Variants: primary | secondary | danger | ghost
// Sizes: sm | md | lg
// States: default | hover | active | disabled | loading
// Props: onClick, disabled, loading, icon, variant, size, className

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  onClick,
  ...props
}: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        px-${size === 'sm' ? '3' : size === 'lg' ? '6' : '4'}
        py-${size === 'sm' ? '1.5' : size === 'lg' ? '3' : '2'}
        rounded-md
        font-medium
        transition-colors
        ${variant === 'primary' && 'bg-accent-blue hover:bg-blue-600'}
        ${variant === 'secondary' && 'bg-bg-tertiary hover:bg-border'}
        ${variant === 'danger' && 'bg-accent-red hover:bg-red-700'}
        ${loading && 'opacity-50 cursor-wait'}
      `}
      {...props}
    >
      {loading ? <Spinner size={size} /> : children}
    </button>
  );
}
```

#### 2. Card
```typescript
export function Card({ children, variant = "default", className }: CardProps) {
  return (
    <div
      className={`
        bg-bg-secondary
        border border-border
        rounded-lg
        p-4
        ${variant === 'hover' && 'hover:border-border-light transition-colors'}
        ${className}
      `}
    >
      {children}
    </div>
  );
}
```

#### 3. Badge
```typescript
// Variants: primary | success | warning | error | info
// Sizes: sm | md | lg

export function Badge({ children, variant = "primary", size = "md" }: BadgeProps) {
  const colors = {
    primary: 'bg-accent-blue/20 text-accent-blue',
    success: 'bg-accent-green/20 text-accent-green',
    warning: 'bg-accent-orange/20 text-accent-orange',
    error: 'bg-accent-red/20 text-accent-red',
    info: 'bg-accent-cyan/20 text-accent-cyan',
  };
  
  return (
    <span className={`
      inline-flex items-center
      px-2 py-1
      rounded-full
      text-xs font-medium
      ${colors[variant]}
    `}>
      {children}
    </span>
  );
}
```

#### 4. Input
```typescript
// Types: text | email | password | number | search | date
// States: default | focus | error | disabled
// Props: value, onChange, placeholder, error, disabled, icon

export function Input({ error, icon: Icon, ...props }: InputProps) {
  return (
    <div className="relative">
      {Icon && <Icon className="absolute left-3 top-3 text-text-secondary" />}
      <input
        {...props}
        className={`
          w-full
          px-${Icon ? '10' : '3'}
          py-2
          bg-bg-tertiary
          border ${error ? 'border-accent-red' : 'border-border'}
          rounded-md
          text-text-primary
          placeholder-text-tertiary
          transition-colors
          focus:outline-none
          focus:border-accent-blue
          focus:ring-2
          focus:ring-accent-blue/20
        `}
      />
    </div>
  );
}
```

#### 5. Modal / Dialog
```typescript
export function Modal({ open, onClose, title, children }: ModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="bg-bg-secondary rounded-lg shadow-xl max-w-md w-full mx-4"
          >
            <div className="flex justify-between items-center p-4 border-b border-border">
              <h2 className="text-lg font-bold">{title}</h2>
              <button onClick={onClose}>✕</button>
            </div>
            <div className="p-4">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
```

#### 6. Spinner / Loading
```typescript
export function Spinner({ size = "md" }: SpinnerProps) {
  const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' };
  
  return (
    <svg
      className={`${sizes[size]} animate-spin text-accent-blue`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
      <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}
```

#### 7. Toast / Notification
```typescript
export function Toast({ message, type = "info", onClose }: ToastProps) {
  const colors = {
    info: 'bg-accent-blue/20 text-accent-blue border-accent-blue',
    success: 'bg-accent-green/20 text-accent-green border-accent-green',
    warning: 'bg-accent-orange/20 text-accent-orange border-accent-orange',
    error: 'bg-accent-red/20 text-accent-red border-accent-red',
  };
  
  return (
    <motion.div
      initial={{ x: 400, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 400, opacity: 0 }}
      className={`p-4 rounded-lg border ${colors[type]}`}
    >
      {message}
    </motion.div>
  );
}
```

#### 8. DataTable
```typescript
// Props: columns, data, sortable, filterable, paginated
export function DataTable({ columns, data, sortable = true }: DataTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            {columns.map(col => (
              <th
                key={col.key}
                className="text-left p-3 text-text-secondary text-sm font-medium"
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={idx} className="border-b border-border hover:bg-bg-tertiary">
              {columns.map(col => (
                <td key={col.key} className="p-3">
                  {row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

#### 9. Tabs
```typescript
export function Tabs({ tabs, defaultTab = 0 }: TabsProps) {
  const [active, setActive] = useState(defaultTab);
  
  return (
    <>
      <div className="flex border-b border-border">
        {tabs.map((tab, idx) => (
          <button
            key={idx}
            onClick={() => setActive(idx)}
            className={`
              px-4 py-2 font-medium
              border-b-2
              transition-colors
              ${active === idx
                ? 'border-accent-blue text-accent-blue'
                : 'border-transparent text-text-secondary hover:text-text-primary'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="mt-4">{tabs[active].content}</div>
    </>
  );
}
```

#### 10. Accordion
```typescript
export function Accordion({ items }: AccordionProps) {
  const [expanded, setExpanded] = useState<number | null>(null);
  
  return (
    <div>
      {items.map((item, idx) => (
        <div key={idx} className="border-b border-border">
          <button
            onClick={() => setExpanded(expanded === idx ? null : idx)}
            className="w-full p-4 flex justify-between items-center hover:bg-bg-tertiary"
          >
            <span className="font-medium">{item.title}</span>
            <span className={`transition-transform ${expanded === idx ? 'rotate-180' : ''}`}>
              ▼
            </span>
          </button>
          {expanded === idx && <div className="p-4 bg-bg-tertiary">{item.content}</div>}
        </div>
      ))}
    </div>
  );
}
```

#### 11. Tooltip
```typescript
export function Tooltip({ content, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  
  return (
    <div className="relative inline-block" onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)}>
      {children}
      {visible && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-text-primary text-bg-primary rounded text-xs whitespace-nowrap">
          {content}
        </div>
      )}
    </div>
  );
}
```

#### 12. Avatar
```typescript
export function Avatar({ src, name, size = "md" }: AvatarProps) {
  const sizes = { sm: 'w-6 h-6', md: 'w-10 h-10', lg: 'w-12 h-12' };
  
  return (
    <img
      src={src || `https://ui-avatars.com/api/?name=${name}`}
      alt={name}
      className={`${sizes[size]} rounded-full object-cover`}
    />
  );
}
```

### Composite Components

#### AgentActivityLog
```typescript
export function AgentActivityLog({ events }: AgentActivityLogProps) {
  return (
    <div className="font-mono text-sm space-y-2 bg-bg-secondary rounded-lg p-4 max-h-96 overflow-y-auto">
      {events.map((event, idx) => (
        <div key={idx} className="flex gap-2">
          <span className="text-accent-cyan">{event.timestamp}</span>
          <span className="text-accent-green">[{event.agent.toUpperCase()}]</span>
          <span className="text-text-primary">{event.message}</span>
        </div>
      ))}
    </div>
  );
}
```

#### MetricsMatrix
```typescript
export function MetricsMatrix() {
  return (
    <div className="grid grid-cols-4 gap-4">
      <Card>
        <div className="text-2xl font-bold text-accent-green">12</div>
        <div className="text-text-secondary text-sm">Opportunities</div>
      </Card>
      <Card>
        <div className="text-2xl font-bold text-accent-blue">87</div>
        <div className="text-text-secondary text-sm">Average Score</div>
      </Card>
      <Card>
        <div className="text-2xl font-bold text-accent-cyan">3</div>
        <div className="text-text-secondary text-sm">Pending</div>
      </Card>
      <Card>
        <div className="text-2xl font-bold text-accent-orange">$28k</div>
        <div className="text-text-secondary text-sm">Pipeline Value</div>
      </Card>
    </div>
  );
}
```

#### DraftApprovalCard
```typescript
export function DraftApprovalCard({ draft, onApprove, onReject }: DraftApprovalCardProps) {
  return (
    <Card variant="hover" className="border-accent-blue/50">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="font-bold text-lg">{draft.opportunity.title}</h3>
          <Badge variant="info">{draft.opportunity.score}/100</Badge>
        </div>
      </div>
      <p className="text-text-secondary text-sm mb-4">{draft.content}</p>
      <div className="flex gap-2">
        <Button variant="primary" onClick={onApprove}>
          Approve & Submit
        </Button>
        <Button variant="secondary" onClick={onReject}>
          Reject
        </Button>
      </div>
    </Card>
  );
}
```

---

## PAGE DESIGNS (13 Pages)

### 1. Dashboard
```
┌───────────────────────────────────────────────────┐
│ Dashboard > Today                      🔔 Settings│
├───────────┬───────────────────────────────────────┤
│ SIDEBAR   │ Agent Activity Log                    │
│           │ 08:47 > [SCORER] analyzing op #42    │
│ ✓ Home    │ 08:48 > [DECISION] decision: do_now  │
│ ◆ Opps    │ 08:49 > [DRAFTER] draft created      │
│ ◆ Jobs    │                                       │
│ ◆ Drafts  ├───────────────────────────────────────┤
│ ◆ Metrics │ Metrics Matrix                        │
│           │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│           │ │  12  │ │  87  │ │   3  │ │ $28k │ │
│           │ │ OPPS │ │SCORE │ │PEND. │ │  $ │ │
│           │ └──────┘ └──────┘ └──────┘ └──────┘ │
│           ├───────────────────────────────────────┤
│           │ Pipeline: [████████░░] 65%            │
│           │ $28,400 committed                     │
└───────────┴───────────────────────────────────────┘
```

**Components:**
- Sidebar (navigation)
- AgentActivityLog (real-time event stream)
- MetricsMatrix (4 KPIs)
- ProgressBar (pipeline visualization)

### 2. Opportunities
```
View: [Grid] [Table]

Filters: [Status ▼] [Score Min ▼] [Deadline ▼]
Sort: [Score ▼]

Grid View:
┌─────────┐ ┌─────────┐ ┌─────────┐
│ Title   │ │ Title   │ │ Title   │
│ Score   │ │ Score   │ │ Score   │
│ Deadline│ │ Deadline│ │ Deadline│
│ $Value  │ │ $Value  │ │ $Value  │
└─────────┘ └─────────┘ └─────────┘

[Click card to open detail panel]
```

**Components:**
- ToggleGroup (Grid/Table view)
- FilterBar (status, score, deadline)
- OpportunityCard (grid view)
- DataTable (table view)
- DetailPanel (side drawer)

### 3. Drafts & Approvals
```
Pending Approvals: 3

[Draft Approval Card 1]
  Title: DevPost Hackathon 2026
  Score: 87/100
  Content: "Your approach leveraging..."
  [Approve & Submit] [Reject]

[Draft Approval Card 2]
  ...

[Draft Approval Card 3]
  ...

Previous Approvals (History):
[Approved on 2026-04-09 - 2pm]
[Approved on 2026-04-08 - 11am]
```

**Components:**
- DraftApprovalCard
- Tabs (Pending/History)
- ApprovalTimeline

### 4. Agent Activity Log (Terminal Style)
```
┌─────────────────────────────────────┐
│ Agent Activity | 2026-04-09         │
├─────────────────────────────────────┤
│ 08:47 > [COMPETITION_SCOUT]         │
│         Found 5 new opportunities   │
│                                     │
│ 08:48 > [SCORER]                   │
│         Scoring: DevPost Hackathon  │
│         Score: 87/100               │
│         └─ High alignment + good    │
│            timing                   │
│                                     │
│ 08:49 > [DECISION_ENGINE]          │
│         Decision: do_now            │
│         Reasoning: High score +     │
│         user capacity available     │
│                                     │
│ 08:50 > [DRAFTER]                  │
│         Draft created               │
│         ID: draft_xy123             │
│                                     │
│ 08:51 > [BRIEFER]                  │
│         Morning briefing sent       │
│         Telegram: @user_bot         │
│                                     │
│ 08:52 > [ERROR] LLAMA TIMEOUT       │
│         Fallback: Together.ai       │
│         Status: Recovered           │
└─────────────────────────────────────┘
```

**Components:**
- ActivityLog (custom, terminal-style)
- Real-time streaming via WebSocket
- Color coding for agent types + status

### 5. Jobs / Contacts / Emails / Metrics / Settings
(Follow similar pattern: Card-based, filterable, real-time updates)

---

## REAL-TIME WEBSOCKET INTEGRATION

### Server Implementation

```python
# backend/app/main.py

from fastapi import WebSocket
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, event: DomainEvent):
        for connection in self.active_connections:
            try:
                await connection.send_json({
                    "type": event.type,
                    "data": event.to_dict(),
                    "timestamp": datetime.now().isoformat()
                })
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/agent-stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Client Implementation

```typescript
// frontend/src/hooks/useAgentStream.ts

import { useEffect, useState, useCallback } from 'react';

interface AgentEvent {
  type: string;
  agent: string;
  message: string;
  timestamp: string;
  data?: Record<string, any>;
}

export function useAgentStream() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/agent-stream');

    ws.onopen = () => {
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const agentEvent: AgentEvent = {
          type: message.type,
          agent: message.data?.agent || 'unknown',
          message: message.data?.message || 'Event',
          timestamp: message.timestamp,
          data: message.data,
        };
        
        setEvents(prev => [agentEvent, ...prev].slice(0, 100)); // Keep last 100
      } catch (e) {
        console.error('Failed to parse message', e);
      }
    };

    ws.onerror = () => {
      setError('WebSocket connection error');
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
      // Attempt reconnect after 3 seconds
      setTimeout(() => {
        // Trigger reconnect
      }, 3000);
    };

    return () => {
      ws.close();
    };
  }, []);

  return { events, connected, error };
}

// Usage in component
function Dashboard() {
  const { events, connected } = useAgentStream();
  
  return (
    <>
      {connected ? <Badge variant="success">Connected</Badge> : <Badge variant="warning">Disconnected</Badge>}
      <AgentActivityLog events={events} />
    </>
  );
}
```

### Event Types

```typescript
type AgentEventType = 
  | 'opportunity.found'
  | 'opportunity.scored'
  | 'opportunity.decided'
  | 'draft.created'
  | 'draft.approved'
  | 'submission.started'
  | 'submission.completed'
  | 'error.occurred'
  | 'agent.started'
  | 'agent.completed';

interface DomainEvent {
  type: AgentEventType;
  agent: string;
  timestamp: string;
  data: {
    opportunity_id?: string;
    score?: number;
    decision?: 'do_now' | 'delay' | 'skip';
    draft_id?: string;
    error_message?: string;
    [key: string]: any;
  };
}
```

---

## REACT ARCHITECTURE

### Folder Structure

```
frontend/src/
├── pages/
│   ├── Dashboard.tsx
│   ├── Opportunities/
│   │   ├── index.tsx
│   │   ├── [id]/detail.tsx
│   │   └── create.tsx
│   ├── Jobs/
│   ├── Contacts/
│   ├── Emails/
│   ├── Drafts/ApprovalsList.tsx
│   ├── Metrics/AnalyticsView.tsx
│   ├── Settings/ProfileSettings.tsx
│   ├── Auth/
│   │   ├── Login.tsx
│   │   ├── Register.tsx
│   │   └── MFA.tsx
│   └── Layout.tsx
│
├── components/
│   ├── Layout/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── MainLayout.tsx
│   ├── Common/
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Badge.tsx
│   │   ├── Modal.tsx
│   │   ├── Input.tsx
│   │   ├── Spinner.tsx
│   │   ├── Toast.tsx
│   │   ├── DataTable.tsx
│   │   ├── Tabs.tsx
│   │   ├── Accordion.tsx
│   │   ├── Tooltip.tsx
│   │   └── Avatar.tsx
│   ├── AgentStream/
│   │   ├── ActivityLog.tsx
│   │   ├── StreamItem.tsx
│   │   └── useAgentStream.ts (moved to hooks)
│   ├── Dashboard/
│   │   ├── MetricsMatrix.tsx
│   │   ├── PipelineBar.tsx
│   │   ├── TopOpportunities.tsx
│   │   └── RecentActivity.tsx
│   └── Charts/
│       ├── LineChart.tsx
│       ├── BarChart.tsx
│       └── PieChart.tsx
│
├── hooks/
│   ├── useAuth.ts
│   ├── useAgentStream.ts
│   ├── useFetch.ts
│   ├── useLocalStorage.ts
│   ├── useNotification.ts
│   └── useTheme.ts
│
├── contexts/
│   ├── AuthContext.tsx
│   ├── ThemeContext.tsx
│   ├── NotificationContext.tsx
│   └── APIContext.tsx
│
├── types/
│   ├── agent.ts
│   ├── opportunity.ts
│   ├── contact.ts
│   ├── submission.ts
│   └── index.ts
│
├── lib/
│   ├── api.ts (HTTP client + React Query)
│   ├── utils.ts
│   ├── formatting.ts
│   ├── constants.ts
│   └── validators.ts
│
├── styles/
│   ├── globals.css (Tailwind imports)
│   ├── animations.css
│   ├── theme.css
│   └── dark-mode.css
│
├── App.tsx
├── index.tsx
└── vite-env.d.ts
```

### State Management Pattern

```typescript
// Server State (React Query)
const useOpportunities = () => {
  return useQuery({
    queryKey: ['opportunities'],
    queryFn: () => api.get('/opportunities'),
  });
};

// Client State (Zustand)
import create from 'zustand';

interface UIStore {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  theme: 'light' | 'dark';
  setTheme: (theme: 'light' | 'dark') => void;
}

const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set(state => ({ sidebarOpen: !state.sidebarOpen })),
  theme: 'dark',
  setTheme: (theme) => set({ theme }),
}));
```

### Performance Optimization

```typescript
// Code splitting by route
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Opportunities = React.lazy(() => import('./pages/Opportunities'));

// Memoization
const OpportunityCard = React.memo(({ opportunity }: OpportunityCardProps) => {
  return <Card>{opportunity.title}</Card>;
});

// Virtual scrolling for long lists
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={opportunities.length}
  itemSize={80}
>
  {({ index, style }) => (
    <div style={style}>
      <OpportunityCard opportunity={opportunities[index]} />
    </div>
  )}
</FixedSizeList>

// Image optimization
<img src={src} alt="..." srcSet={`${src}?w=400 400w, ${src}?w=800 800w`} />

// Bundle analysis
// Use vite-plugin-visualizer to identify large chunks
```

---

## TESTING STRATEGY

### Unit Tests (Vitest + React Testing Library)

```typescript
// frontend/src/components/__tests__/Button.test.tsx

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';

describe('Button', () => {
  it('renders with label', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('calls onClick when clicked', async () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click</Button>);
    
    await userEvent.click(screen.getByText('Click'));
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('is disabled when loading', () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('shows spinner when loading', () => {
    render(<Button loading>Load</Button>);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
```

### Integration Tests (Cypress)

```typescript
// frontend/cypress/e2e/approvals.cy.ts

describe('Drafts & Approvals Flow', () => {
  beforeEach(() => {
    cy.login();
    cy.visit('/drafts');
  });

  it('user can approve a draft', () => {
    cy.get('[data-testid="approval-card"]').first().within(() => {
      cy.get('button').contains('Approve & Submit').click();
    });

    cy.get('[data-testid="toast"]').should('contain', 'Draft approved');
    cy.get('[data-testid="approval-card"]').should('have.length', 2);
  });

  it('user can reject a draft', () => {
    cy.get('[data-testid="approval-card"]').first().within(() => {
      cy.get('button').contains('Reject').click();
    });

    cy.get('[data-testid="modal"]').should('exist');
    cy.get('textarea[placeholder="Reason"]').type('Not the right fit');
    cy.get('button').contains('Confirm').click();
  });
});
```

### E2E Tests (Full User Journeys)

```typescript
describe('Complete Workflow', () => {
  it('opportunity flows from discovery to submission', () => {
    cy.login();
    cy.visit('/dashboard');
    
    // Wait for opportunity.found event
    cy.get('[data-testid="activity-log"]').should('contain', 'Found');
    
    // Navigate to opportunities
    cy.get('a').contains('Opportunities').click();
    
    // View top-scored opportunity
    cy.get('[data-testid="opportunity-card"]').first().click();
    cy.get('[data-testid="detail-panel"]').should('be.visible');
    
    // Approve draft
    cy.get('[data-testid="draft-section"]').within(() => {
      cy.get('button').contains('Approve').click();
    });
    
    // Verify in submissions
    cy.get('a').contains('Metrics').click();
    cy.get('[data-testid="submission-status"]').should('contain', '1 active');
  });
});
```

---

## ACCESSIBILITY (WCAG 2.1 AA)

### Requirements
- Semantic HTML (no div-only layouts)
- ARIA labels on interactive elements
- Color contrast 4.5:1 for text
- Focus indicators visible (min 2px outline)
- Keyboard navigation (Tab, Enter, Esc, Arrow keys)
- Screen reader support (alt text, labels)
- Form validation messages
- Error announcements

### Audit Checklist
- [ ] axe DevTools automated scan (0 critical)
- [ ] Manual NVDA/JAWS testing
- [ ] Keyboard-only navigation
- [ ] Color contrast verification
- [ ] Focus management
- [ ] Mobile accessibility (touch targets min 44x44px)

---

## DEPLOYMENT & PERFORMANCE

### Build Optimization
```bash
# Vite build
bun run build

# Output should be:
# dist/index.html (3KB)
# dist/assets/app-[hash].js (~150KB gzipped)
# dist/assets/vendor-[hash].js (~200KB gzipped)
# Total: < 500KB gzipped
```

### Performance Targets (Lighthouse)
- Performance: 90+
- Accessibility: 95+
- Best Practices: 95+
- SEO: 90+

### Metrics
- **LCP** (Largest Contentful Paint): < 2.5s
- **FID** (First Input Delay): < 100ms
- **CLS** (Cumulative Layout Shift): < 0.1
- **TTFB** (Time to First Byte): < 600ms

### CDN & Caching
- HTML: Cache 5 minutes (no-cache header)
- JS/CSS: Cache 1 year (hash-based)
- Images: Cache 30 days
- API: Cache per endpoint (e.g., opportunities list: 5 min)

### Monitoring
- Sentry for error tracking
- LogRocket for session replay (optional)
- Web Vitals via Google Analytics

---

## SUCCESS CRITERIA

### Phase 2 Completion
- [ ] A+C design system fully implemented
- [ ] All 13 pages redesigned + functional
- [ ] Storybook with 40+ components documented
- [ ] WebSocket real-time agent streams working
- [ ] Dark mode + light mode toggle
- [ ] WCAG 2.1 AA accessibility verified
- [ ] Component test coverage: 80%+
- [ ] Lighthouse 90+ all metrics
- [ ] Bundle < 500KB gzipped
- [ ] LCP < 2.5s, FID < 100ms
- [ ] Mobile responsive (iPad, iPhone tested)
- [ ] Cross-browser tested (Chrome, Firefox, Safari, Edge)

---

## TIMELINE (4-6 weeks)

**Week 1-2: Design System & Components**
- [ ] Tailwind config with A+C colors
- [ ] 40+ base components in Storybook
- [ ] Accessibility audit

**Week 2-3: Page Implementations**
- [ ] Dashboard + Sidebar
- [ ] Opportunities list/detail
- [ ] Drafts & approvals
- [ ] Jobs, Contacts, Emails pages

**Week 3-4: Real-Time & Polish**
- [ ] WebSocket integration
- [ ] Agent activity stream
- [ ] Notifications
- [ ] Dark mode toggle
- [ ] Error boundary + fallbacks

**Week 4-5: Testing & Optimization**
- [ ] Component unit tests (80%+ coverage)
- [ ] Integration tests (critical flows)
- [ ] E2E tests (main journeys)
- [ ] Performance optimization
- [ ] Bundle size reduction

**Week 5-6: Deployment & Launch**
- [ ] Lighthouse audit (90+)
- [ ] Accessibility audit (WCAG AA)
- [ ] Cross-browser testing
- [ ] Production deployment
- [ ] Monitoring setup

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-09  
**Status:** Ready for implementation
