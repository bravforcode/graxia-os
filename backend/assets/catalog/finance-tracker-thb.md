# finance-tracker-thb delivery bundle

This bundle contains the original AI Factory delivery assets.
Source files are preserved below with their relative paths.

## Source: `downloads/09-finance-tracker-thb.html`

```html
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Personal Finance Tracker THB — วางแผนการเงินอัจฉริยะ</title>
<style>
  :root {
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-2: #334155;
    --primary: #3b82f6;
    --primary-light: #60a5fa;
    --success: #22c55e;
    --success-light: #4ade80;
    --danger: #ef4444;
    --danger-light: #f87171;
    --warning: #f59e0b;
    --warning-light: #fbbf24;
    --text: #f1f5f9;
    --text-dim: #94a3b8;
    --border: #475569;
    --radius: 12px;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', 'Noto Sans Thai', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
  
  /* Header */
  header {
    background: linear-gradient(135deg, #1e40af 0%, #7c3aed 100%);
    padding: 24px 0;
    box-shadow: var(--shadow);
    margin-bottom: 24px;
  }
  header h1 {
    font-size: 28px;
    font-weight: 700;
    color: white;
    margin-bottom: 4px;
  }
  header .subtitle {
    color: rgba(255,255,255,0.8);
    font-size: 14px;
  }
  .lang-toggle {
    float: right;
    background: rgba(255,255,255,0.15);
    color: white;
    border: 1px solid rgba(255,255,255,0.3);
    padding: 8px 14px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    margin-top: 4px;
  }
  .lang-toggle:hover { background: rgba(255,255,255,0.25); }
  
  /* Tabs */
  .tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    background: var(--surface);
    padding: 6px;
    border-radius: var(--radius);
    overflow-x: auto;
  }
  .tab {
    flex: 1;
    min-width: 120px;
    padding: 12px 20px;
    background: transparent;
    color: var(--text-dim);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
    white-space: nowrap;
  }
  .tab:hover { color: var(--text); background: var(--surface-2); }
  .tab.active {
    background: var(--primary);
    color: white;
  }
  .tab-content { display: none; }
  .tab-content.active { display: block; animation: fadeIn 0.3s; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  
  /* Cards & Grid */
  .card {
    background: var(--surface);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: var(--shadow);
    border: 1px solid var(--border);
  }
  .card h2, .card h3 {
    color: var(--text);
    margin-bottom: 12px;
  }
  .card h2 { font-size: 20px; }
  .card h3 { font-size: 16px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
  
  .grid {
    display: grid;
    gap: 16px;
  }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }
  @media (max-width: 768px) {
    .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
  }
  
  /* Stat Cards */
  .stat {
    background: var(--surface);
    padding: 20px;
    border-radius: var(--radius);
    border-left: 4px solid var(--primary);
    box-shadow: var(--shadow);
  }
  .stat.income { border-left-color: var(--success); }
  .stat.expense { border-left-color: var(--danger); }
  .stat.balance { border-left-color: var(--warning); }
  .stat.tax { border-left-color: #a855f7; }
  .stat .label {
    color: var(--text-dim);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
  }
  .stat .value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text);
  }
  .stat.income .value { color: var(--success-light); }
  .stat.expense .value { color: var(--danger-light); }
  .stat.balance .value { color: var(--warning-light); }
  .stat.tax .value { color: #c084fc; }
  .stat .sublabel { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
  
  /* Forms */
  .form-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 12px;
  }
  label {
    display: block;
    color: var(--text-dim);
    font-size: 13px;
    margin-bottom: 4px;
    font-weight: 500;
  }
  input, select, textarea {
    width: 100%;
    padding: 10px 12px;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 14px;
    font-family: inherit;
    transition: border 0.2s;
  }
  input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--primary);
  }
  textarea { min-height: 60px; resize: vertical; }
  
  .btn {
    padding: 10px 20px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .btn:hover { background: var(--primary-light); transform: translateY(-1px); }
  .btn-danger { background: var(--danger); }
  .btn-danger:hover { background: var(--danger-light); }
  .btn-success { background: var(--success); }
  .btn-success:hover { background: var(--success-light); }
  .btn-secondary { background: var(--surface-2); }
  .btn-secondary:hover { background: var(--border); }
  .btn-small { padding: 6px 12px; font-size: 12px; }
  
  /* Tables */
  .table-wrap { overflow-x: auto; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
  }
  th {
    text-align: left;
    padding: 12px;
    background: var(--surface-2);
    color: var(--text-dim);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  tr:hover td { background: var(--surface-2); }
  .amount-income { color: var(--success-light); font-weight: 600; }
  .amount-expense { color: var(--danger-light); font-weight: 600; }
  .actions { display: flex; gap: 6px; }
  .badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    background: var(--surface-2);
    color: var(--text-dim);
  }
  
  /* Progress bar */
  .progress {
    background: var(--bg);
    height: 24px;
    border-radius: 12px;
    overflow: hidden;
    position: relative;
    border: 1px solid var(--border);
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--primary), var(--primary-light));
    transition: width 0.5s;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 12px;
    font-weight: 600;
  }
  .progress-fill.success { background: linear-gradient(90deg, var(--success), var(--success-light)); }
  .progress-fill.warning { background: linear-gradient(90deg, var(--warning), var(--warning-light)); }
  .progress-fill.danger { background: linear-gradient(90deg, var(--danger), var(--danger-light)); }
  
  /* Chart container */
  .chart-container {
    width: 100%;
    height: 280px;
    background: var(--bg);
    border-radius: 8px;
    padding: 12px;
    border: 1px solid var(--border);
  }
  
  /* Toast */
  .toast {
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 14px 20px;
    background: var(--surface);
    color: var(--text);
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    border-left: 4px solid var(--success);
    z-index: 1000;
    transform: translateX(400px);
    transition: transform 0.3s;
    max-width: 320px;
  }
  .toast.show { transform: translateX(0); }
  .toast.error { border-left-color: var(--danger); }
  .toast.warning { border-left-color: var(--warning); }
  
  /* Goal cards */
  .goal-card {
    background: var(--bg);
    padding: 16px;
    border-radius: 8px;
    border: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .goal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .goal-name { font-size: 16px; font-weight: 600; }
  .goal-amount { color: var(--primary-light); font-weight: 600; }
  
  /* Empty state */
  .empty {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-dim);
  }
  .empty-icon { font-size: 48px; opacity: 0.3; margin-bottom: 12px; }
  
  /* Tax bracket */
  .tax-bracket {
    display: flex;
    justify-content: space-between;
    padding: 8px 12px;
    background: var(--bg);
    border-radius: 6px;
    margin-bottom: 4px;
    font-size: 13px;
  }
  .tax-bracket.active { background: var(--primary); color: white; }
  .tax-bracket .rate { font-weight: 600; }
  
  /* Modal */
  .modal-bg {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .modal-bg.show { display: flex; }
  .modal {
    background: var(--surface);
    padding: 24px;
    border-radius: var(--radius);
    max-width: 400px;
    width: 90%;
    border: 1px solid var(--border);
  }
  .modal h3 { margin-bottom: 16px; }
  
  .flex { display: flex; gap: 8px; align-items: center; }
  .flex-between { display: flex; justify-content: space-between; align-items: center; }
  .mt-2 { margin-top: 8px; }
  .mt-4 { margin-top: 16px; }
  .mb-2 { margin-bottom: 8px; }
  .text-dim { color: var(--text-dim); }
  .text-success { color: var(--success-light); }
  .text-danger { color: var(--danger-light); }
  .text-warning { color: var(--warning-light); }
  .small { font-size: 12px; }
</style>
</head>
<body>
<header>
  <div class="container">
    <button class="lang-toggle" onclick="toggleLang()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><path d="M2 12h20M12 2c3 3 4.5 6 4.5 10s-1.5 7-4.5 10c-3-3-4.5-6-4.5-10s1.5-7 4.5-10z" fill="none" stroke="currentColor" stroke-width="2"/></svg> EN / TH</button>
    <h1 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.94s4.18 1.36 4.18 3.85c-.01 1.83-1.38 2.83-3.12 3.19z"/></svg> Personal Finance Tracker THB" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.94s4.18 1.36 4.18 3.85c-.01 1.83-1.38 2.83-3.12 3.19z"/></svg> Personal Finance Tracker THB"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.94s4.18 1.36 4.18 3.85c-.01 1.83-1.38 2.83-3.12 3.19z"/></svg> Personal Finance Tracker THB</h1>
    <p class="subtitle" data-th="วางแผนการเงินอัจฉริยะ — รองรับภาษีไทย 2026" data-en="Smart Personal Finance — Thai Tax 2026 Compliant">วางแผนการเงินอัจฉริยะ — รองรับภาษีไทย 2026</p>
  </div>
</header>

<div class="container">
  <!-- Tabs -->
  <div class="tabs">
    <button class="tab active" data-tab="dashboard" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> Dashboard" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> Dashboard"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> Dashboard</button>
    <button class="tab" data-tab="income" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายรับ" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> Income"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายรับ</button>
    <button class="tab" data-tab="expense" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายจ่าย" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> Expenses"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายจ่าย</button>
    <button class="tab" data-tab="tax" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> ภาษี" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> Tax"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> ภาษี</button>
    <button class="tab" data-tab="goals" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> เป้าหมาย" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> Goals"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> เป้าหมาย</button>
    <button class="tab" data-tab="settings" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> ตั้งค่า" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> Settings"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> ตั้งค่า</button>
  </div>

  <!-- DASHBOARD -->
  <div id="dashboard" class="tab-content active">
    <div class="grid grid-4">
      <div class="stat income">
        <div class="label" data-th="รายรับเดือนนี้" data-en="Income This Month">รายรับเดือนนี้</div>
        <div class="value" id="stat-income">฿0</div>
        <div class="sublabel" id="stat-income-count">0 รายการ</div>
      </div>
      <div class="stat expense">
        <div class="label" data-th="รายจ่ายเดือนนี้" data-en="Expenses This Month">รายจ่ายเดือนนี้</div>
        <div class="value" id="stat-expense">฿0</div>
        <div class="sublabel" id="stat-expense-count">0 รายการ</div>
      </div>
      <div class="stat balance">
        <div class="label" data-th="คงเหลือ" data-en="Balance">คงเหลือ</div>
        <div class="value" id="stat-balance">฿0</div>
        <div class="sublabel" id="stat-savings-rate">ออม 0%</div>
      </div>
      <div class="stat tax">
        <div class="label" data-th="ภาษีประมาณการ/ปี" data-en="Est. Annual Tax">ภาษีประมาณการ/ปี</div>
        <div class="value" id="stat-tax">฿0</div>
        <div class="sublabel" data-th="อัปเดตจากข้อมูล" data-en="Updated from data">อัปเดตจากข้อมูล</div>
      </div>
    </div>

    <div class="grid grid-2 mt-4">
      <div class="card">
        <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6h-6z"/></svg> แนวโน้ม 12 เดือน" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6h-6z"/></svg> 12-Month Trend"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6h-6z"/></svg> แนวโน้ม 12 เดือน</h3>
        <div class="chart-container" id="chart-trend"></div>
      </div>
      <div class="card">
        <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/></svg> รายจ่ายตามหมวด" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/></svg> Expenses by Category"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93z"/></svg> รายจ่ายตามหมวด</h3>
        <div class="chart-container" id="chart-category"></div>
      </div>
    </div>

    <div class="card mt-4">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> ธุรกรรมล่าสุด" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> Recent Transactions"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> ธุรกรรมล่าสุด</h3>
      <div class="table-wrap">
        <table id="table-recent">
          <thead>
            <tr>
              <th data-th="วันที่" data-en="Date">วันที่</th>
              <th data-th="ประเภท" data-en="Type">ประเภท</th>
              <th data-th="หมวด" data-en="Category">หมวด</th>
              <th data-th="รายละเอียด" data-en="Description">รายละเอียด</th>
              <th data-th="จำนวน" data-en="Amount">จำนวน</th>
              <th data-th="จัดการ" data-en="Actions">จัดการ</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- INCOME -->
  <div id="income" class="tab-content">
    <div class="card">
      <h2 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> เพิ่มรายรับ" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> Add Income"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> เพิ่มรายรับ</h2>
      <form id="form-income">
        <div class="form-row">
          <div>
            <label data-th="วันที่" data-en="Date">วันที่</label>
            <input type="date" id="income-date" required>
          </div>
          <div>
            <label data-th="แหล่งที่มา" data-en="Source">แหล่งที่มา</label>
            <input type="text" id="income-source" placeholder="เช่น บริษัท ABC" required>
          </div>
          <div>
            <label data-th="ประเภท" data-en="Type">ประเภท</label>
            <select id="income-type" required>
              <option value="Salary">Salary / เงินเดือน</option>
              <option value="Freelance">Freelance / ฟรีแลนซ์</option>
              <option value="Bonus">Bonus / โบนัส</option>
              <option value="Investment">Investment / การลงทุน</option>
              <option value="Other">Other / อื่น ๆ</option>
            </select>
          </div>
          <div>
            <label data-th="จำนวน (บาท)" data-en="Amount (THB)">จำนวน (บาท)</label>
            <input type="number" id="income-amount" min="0" step="0.01" required>
          </div>
        </div>
        <div class="form-row">
          <div>
            <label data-th="หัก ณ ที่จ่าย (บาท)" data-en="Tax Withheld (THB)">หัก ณ ที่จ่าย (บาท)</label>
            <input type="number" id="income-tax" min="0" step="0.01" value="0">
          </div>
          <div style="grid-column: span 2;">
            <label data-th="หมายเหตุ" data-en="Notes">หมายเหตุ</label>
            <input type="text" id="income-notes" placeholder="เช่น เงินเดือนประจำเดือน">
          </div>
        </div>
        <button type="submit" class="btn btn-success" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกรายรับ" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save Income"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกรายรับ</button>
      </form>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> รายการรายรับทั้งหมด" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> All Income"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> รายการรายรับทั้งหมด</h3>
      <div class="table-wrap">
        <table id="table-income">
          <thead>
            <tr>
              <th data-th="วันที่" data-en="Date">วันที่</th>
              <th data-th="แหล่งที่มา" data-en="Source">แหล่งที่มา</th>
              <th data-th="ประเภท" data-en="Type">ประเภท</th>
              <th data-th="Gross" data-en="Gross">Gross</th>
              <th data-th="หักภาษี" data-en="Tax">หักภาษี</th>
              <th data-th="Net" data-en="Net">Net</th>
              <th data-th="หมายเหตุ" data-en="Notes">หมายเหตุ</th>
              <th data-th="ลบ" data-en="Delete">ลบ</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- EXPENSE -->
  <div id="expense" class="tab-content">
    <div class="card">
      <h2 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> เพิ่มรายจ่าย" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> Add Expense"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg> เพิ่มรายจ่าย</h2>
      <form id="form-expense">
        <div class="form-row">
          <div>
            <label data-th="วันที่" data-en="Date">วันที่</label>
            <input type="date" id="expense-date" required>
          </div>
          <div>
            <label data-th="หมวด" data-en="Category">หมวด</label>
            <select id="expense-category" required>
              <option value="Food">Food / อาหาร</option>
              <option value="Transport">Transport / เดินทาง</option>
              <option value="Housing">Housing / ที่อยู่อาศัย</option>
              <option value="Health">Health / สุขภาพ</option>
              <option value="Education">Education / การศึกษา</option>
              <option value="Entertainment">Entertainment / บันเทิง</option>
              <option value="Shopping">Shopping / ช้อปปิ้ง</option>
              <option value="Utilities">Utilities / สาธารณูปโภค</option>
              <option value="Insurance">Insurance / ประกัน</option>
              <option value="Other">Other / อื่น ๆ</option>
            </select>
          </div>
          <div>
            <label data-th="จำนวน (บาท)" data-en="Amount (THB)">จำนวน (บาท)</label>
            <input type="number" id="expense-amount" min="0" step="0.01" required>
          </div>
          <div>
            <label data-th="วิธีชำระ" data-en="Payment Method">วิธีชำระ</label>
            <select id="expense-payment" required>
              <option value="Cash">Cash / เงินสด</option>
              <option value="Bank Transfer">Bank Transfer / โอน</option>
              <option value="Credit Card">Credit Card / บัตรเครดิต</option>
              <option value="PromptPay">PromptPay</option>
              <option value="TrueMoney">TrueMoney</option>
              <option value="Other">Other / อื่น ๆ</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div style="grid-column: span 3;">
            <label data-th="รายละเอียด" data-en="Description">รายละเอียด</label>
            <input type="text" id="expense-desc" placeholder="เช่น กับข้าวที่ตลาด" required>
          </div>
        </div>
        <button type="submit" class="btn btn-danger" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกรายจ่าย" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save Expense"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกรายจ่าย</button>
      </form>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> รายการรายจ่ายทั้งหมด" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> All Expenses"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> รายการรายจ่ายทั้งหมด</h3>
      <div class="table-wrap">
        <table id="table-expense">
          <thead>
            <tr>
              <th data-th="วันที่" data-en="Date">วันที่</th>
              <th data-th="หมวด" data-en="Category">หมวด</th>
              <th data-th="รายละเอียด" data-en="Description">รายละเอียด</th>
              <th data-th="จำนวน" data-en="Amount">จำนวน</th>
              <th data-th="ชำระ" data-en="Payment">ชำระ</th>
              <th data-th="ลบ" data-en="Delete">ลบ</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAX -->
  <div id="tax" class="tab-content">
    <div class="card">
      <h2 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> คำนวณภาษีเงินได้บุคคลธรรมดา 2026" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> Thai Personal Income Tax 2026"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> คำนวณภาษีเงินได้บุคคลธรรมดา 2026</h2>
      <div class="grid grid-2">
        <div>
          <div class="form-row">
            <div>
              <label data-th="รายได้รวมทั้งปี (Gross)" data-en="Annual Gross Income">รายได้รวมทั้งปี (Gross)</label>
              <input type="number" id="tax-gross" min="0" step="1000" value="0">
            </div>
            <div>
              <label data-th="หัก ณ ที่จ่ายสะสม" data-en="Tax Withheld YTD">หัก ณ ที่จ่ายสะสม</label>
              <input type="number" id="tax-withheld" min="0" step="1000" value="0">
            </div>
          </div>
          <div class="form-row">
            <div>
              <label data-th="ประกันสังคม (สูงสุด 9,000/ปี)" data-en="Social Security (max 9,000)">ประกันสังคม (สูงสุด 9,000/ปี)</label>
              <input type="number" id="tax-sso" min="0" max="9000" step="100" value="9000">
            </div>
            <div>
              <label data-th="เงินบริจาค" data-en="Donations">เงินบริจาค</label>
              <input type="number" id="tax-donation" min="0" step="100" value="0">
            </div>
          </div>
          <button class="btn mt-2" onclick="recalcTax()" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg> คำนวณใหม่" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg> Recalculate"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg> คำนวณใหม่</button>
        </div>
        <div>
          <div class="grid grid-2">
            <div class="stat">
              <div class="label" data-th="รายได้สุทธิ" data-en="Net Income">รายได้สุทธิ</div>
              <div class="value" id="tax-net" style="font-size: 22px;">฿0</div>
            </div>
            <div class="stat tax">
              <div class="label" data-th="ภาษีที่ต้องจ่าย" data-en="Tax Owed">ภาษีที่ต้องจ่าย</div>
              <div class="value" id="tax-owed" style="font-size: 22px;">฿0</div>
            </div>
          </div>
          <div class="card mt-4" style="background: var(--bg);">
            <div class="flex-between">
              <span data-th="หัก ณ ที่จ่ายไปแล้ว" data-en="Already Withheld">หัก ณ ที่จ่ายไปแล้ว</span>
              <strong id="tax-paid">฿0</strong>
            </div>
            <hr style="border-color: var(--border); margin: 8px 0;">
            <div class="flex-between">
              <strong data-th="ต้องจ่ายเพิ่ม / ได้คืน" data-en="Tax Due / Refund">ต้องจ่ายเพิ่ม / ได้คืน</strong>
              <strong id="tax-due" style="font-size: 20px;">฿0</strong>
            </div>
            <div class="text-dim small mt-2" id="tax-status" data-th="กรอกข้อมูลเพื่อคำนวณ" data-en="Enter data to calculate">กรอกข้อมูลเพื่อคำนวณ</div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> อัตราภาษีแบบขั้นบันได (Progressive Tax 2026)" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> Progressive Tax Brackets 2026"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> อัตราภาษีแบบขั้นบันได (Progressive Tax 2026)</h3>
      <div id="tax-brackets" class="mt-2"></div>
      <p class="text-dim small mt-4" data-th="ค่าลดหย่อนส่วนตัว 60,000 บาท/ปี | ประกันสังคมสูงสุด 9,000 บาท/ปี" data-en="Personal allowance 60,000 THB/yr | Social Security max 9,000 THB/yr">ค่าลดหย่อนส่วนตัว 60,000 บาท/ปี | ประกันสังคมสูงสุด 9,000 บาท/ปี</p>
    </div>
  </div>

  <!-- GOALS -->
  <div id="goals" class="tab-content">
    <div class="card">
      <h2 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> เพิ่มเป้าหมายการออม" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> Add Savings Goal"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> เพิ่มเป้าหมายการออม</h2>
      <form id="form-goal">
        <div class="form-row">
          <div>
            <label data-th="ชื่อเป้าหมาย" data-en="Goal Name">ชื่อเป้าหมาย</label>
            <input type="text" id="goal-name" placeholder="เช่น Emergency Fund" required>
          </div>
          <div>
            <label data-th="เป้าหมาย (บาท)" data-en="Target (THB)">เป้าหมาย (บาท)</label>
            <input type="number" id="goal-target" min="1" step="1000" required>
          </div>
          <div>
            <label data-th="ออมแล้ว (บาท)" data-en="Current (THB)">ออมแล้ว (บาท)</label>
            <input type="number" id="goal-current" min="0" step="1000" value="0">
          </div>
          <div>
            <label data-th="ออม/เดือน (บาท)" data-en="Monthly (THB)">ออม/เดือน (บาท)</label>
            <input type="number" id="goal-monthly" min="0" step="100" value="0">
          </div>
        </div>
        <button type="submit" class="btn btn-success" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกเป้าหมาย" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save Goal"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกเป้าหมาย</button>
      </form>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> เป้าหมายของฉัน" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> My Goals"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> เป้าหมายของฉัน</h3>
      <div id="goals-list"></div>
    </div>
  </div>

  <!-- SETTINGS -->
  <div id="settings" class="tab-content">
    <div class="card">
      <h2 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> ตั้งค่าทั่วไป" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> General Settings"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg> ตั้งค่าทั่วไป</h2>
      <div class="form-row">
        <div>
          <label data-th="งบรายจ่าย/เดือน" data-en="Monthly Budget">งบรายจ่าย/เดือน</label>
          <input type="number" id="set-budget" min="0" step="1000" value="20000">
        </div>
        <div>
          <label data-th="เป้าออม (%)" data-en="Savings Target (%)">เป้าออม (%)</label>
          <input type="number" id="set-savings-target" min="0" max="100" step="1" value="20">
        </div>
        <div>
          <label data-th="ค่าลดหย่อนส่วนตัว" data-en="Personal Allowance">ค่าลดหย่อนส่วนตัว</label>
          <input type="number" id="set-allowance" min="0" step="1000" value="60000">
        </div>
      </div>
      <button class="btn mt-2" onclick="saveSettings()" data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกการตั้งค่า" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save Settings"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> บันทึกการตั้งค่า</button>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> ข้อมูล" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Data"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> ข้อมูล</h3>
      <div class="flex" style="flex-wrap: wrap; gap: 8px;">
        <button class="btn" onclick="exportCSV()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Export CSV</button>
        <button class="btn btn-secondary" onclick="exportJSON()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Export JSON</button>
        <button class="btn btn-secondary" onclick="document.getElementById('import-file').click()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z"/></svg> Import JSON</button>
        <input type="file" id="import-file" style="display:none" accept=".json" onchange="importJSON(event)">
        <button class="btn btn-secondary" onclick="loadSampleData()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> โหลดข้อมูลตัวอย่าง</button>
        <button class="btn btn-danger" onclick="clearAllData()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg> ลบข้อมูลทั้งหมด</button>
      </div>
    </div>

    <div class="card">
      <h3 data-th="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg> เกี่ยวกับ" data-en="<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg> About"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg> เกี่ยวกับ</h3>
      <p class="text-dim" data-th="Personal Finance Tracker THB v1.0 — เก็บข้อมูลใน localStorage ของเบราว์เซอร์เท่านั้น ไม่มีการส่งข้อมูลออกไปไหน" data-en="Personal Finance Tracker THB v1.0 — Data stored in browser localStorage only, nothing is sent externally">Personal Finance Tracker THB v1.0 — เก็บข้อมูลใน localStorage ของเบราว์เซอร์เท่านั้น ไม่มีการส่งข้อมูลออกไปไหน</p>
      <p class="text-dim small mt-2" data-th="License: สำหรับผู้ซื้อ license 1 คน | © 2026" data-en="License: 1 user per license | © 2026">License: สำหรับผู้ซื้อ license 1 คน | © 2026</p>
    </div>
  </div>
</div>

<!-- Toast notification -->
<div id="toast" class="toast"></div>

<script>
/* ============================================
   Personal Finance Tracker THB - Vanilla JS
   ============================================ */

// ----- State -----
let state = {
  income: [],
  expense: [],
  goals: [],
  settings: {
    monthlyBudget: 20000,
    savingsTargetPct: 20,
    personalAllowance: 60000,
    language: 'th'
  }
};

// ----- Thai Tax Brackets 2026 -----
const TAX_BRACKETS = [
  { min: 0, max: 150000, rate: 0 },
  { min: 150000, max: 300000, rate: 0.05 },
  { min: 300000, max: 500000, rate: 0.10 },
  { min: 500000, max: 750000, rate: 0.15 },
  { min: 750000, max: 1000000, rate: 0.20 },
  { min: 1000000, max: 2000000, rate: 0.25 },
  { min: 2000000, max: 4000000, rate: 0.30 },
  { min: 4000000, max: Infinity, rate: 0.35 }
];

// ----- Storage -----
function save() {
  try {
    localStorage.setItem('financeTracker', JSON.stringify(state));
  } catch (e) {
    toast('Error saving data: ' + e.message, 'error');
  }
}

function load() {
  try {
    const data = localStorage.getItem('financeTracker');
    if (data) {
      const parsed = JSON.parse(data);
      state = { ...state, ...parsed, settings: { ...state.settings, ...(parsed.settings || {}) } };
    }
  } catch (e) {
    console.error('Load error', e);
  }
}

// ----- Formatting -----
function fmt(n) {
  return '฿' + Math.round(n).toLocaleString('th-TH');
}
function fmtNum(n) {
  return Math.round(n).toLocaleString('th-TH');
}
function todayISO() { return new Date().toISOString().split('T')[0]; }

// ----- Tax calculation -----
function calcTax(netIncome) {
  let tax = 0;
  for (const b of TAX_BRACKETS) {
    if (netIncome > b.min) {
      const taxable = Math.min(netIncome, b.max) - b.min;
      tax += taxable * b.rate;
    }
    if (netIncome <= b.max) break;
  }
  return tax;
}

function recalcTax() {
  const gross = parseFloat(document.getElementById('tax-gross').value) || 0;
  const withheld = parseFloat(document.getElementById('tax-withheld').value) || 0;
  const sso = Math.min(9000, parseFloat(document.getElementById('tax-sso').value) || 0);
  const donation = Math.min(gross * 0.1, parseFloat(document.getElementById('tax-donation').value) || 0);
  const allowance = state.settings.personalAllowance;
  
  const net = Math.max(0, gross - allowance - sso - donation);
  const owed = calcTax(net);
  const due = owed - withheld;
  
  document.getElementById('tax-net').textContent = fmt(net);
  document.getElementById('tax-owed').textContent = fmt(owed);
  document.getElementById('tax-paid').textContent = fmt(withheld);
  
  const dueEl = document.getElementById('tax-due');
  dueEl.textContent = fmt(Math.abs(due));
  dueEl.className = due >= 0 ? 'text-danger' : 'text-success';
  dueEl.style.fontSize = '20px';
  
  const statusEl = document.getElementById('tax-status');
  if (due > 0) {
    statusEl.innerHTML = `<span class="text-danger">ต้องจ่ายเพิ่ม ${fmt(due)} บาท</span>`;
  } else if (due < 0) {
    statusEl.innerHTML = `<span class="text-success">ได้คืน ${fmt(Math.abs(due))} บาท</span>`;
  } else {
    statusEl.innerHTML = `<span class="text-dim">พอดี ไม่ต้องจ่ายเพิ่ม/ได้คืน</span>`;
  }
  
  renderTaxBrackets(net);
}

function renderTaxBrackets(netIncome) {
  const container = document.getElementById('tax-brackets');
  container.innerHTML = TAX_BRACKETS.map(b => {
    const isActive = netIncome > b.min;
    const maxStr = b.max === Infinity ? '4M+' : fmt(b.max);
    return `<div class="tax-bracket ${isActive ? 'active' : ''}">
      <span>${fmt(b.min)} - ${maxStr}</span>
      <span class="rate">${(b.rate * 100).toFixed(0)}%</span>
    </div>`;
  }).join('');
}

// ----- Tabs -----
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.tab).classList.add('active');
  });
});

// ----- Income Form -----
document.getElementById('form-income').addEventListener('submit', e => {
  e.preventDefault();
  const entry = {
    id: Date.now(),
    date: document.getElementById('income-date').value,
    source: document.getElementById('income-source').value,
    type: document.getElementById('income-type').value,
    gross: parseFloat(document.getElementById('income-amount').value) || 0,
    tax: parseFloat(document.getElementById('income-tax').value) || 0,
    net: (parseFloat(document.getElementById('income-amount').value) || 0) - (parseFloat(document.getElementById('income-tax').value) || 0),
    notes: document.getElementById('income-notes').value
  };
  state.income.push(entry);
  save();
  renderIncome();
  renderDashboard();
  renderRecent();
  e.target.reset();
  document.getElementById('income-date').value = todayISO();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> บันทึกรายรับเรียบร้อย');
});

function renderIncome() {
  const tbody = document.querySelector('#table-income tbody');
  if (state.income.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg></div>ยังไม่มีข้อมูลรายรับ</td></tr>';
    return;
  }
  tbody.innerHTML = [...state.income].reverse().map(i => `
    <tr>
      <td>${i.date}</td>
      <td>${escapeHtml(i.source)}</td>
      <td><span class="badge">${i.type}</span></td>
      <td class="amount-income">${fmt(i.gross)}</td>
      <td>${fmt(i.tax)}</td>
      <td class="amount-income">${fmt(i.net)}</td>
      <td class="text-dim small">${escapeHtml(i.notes || '-')}</td>
      <td><button class="btn btn-danger btn-small" onclick="deleteIncome(${i.id})"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button></td>
    </tr>
  `).join('');
}

function deleteIncome(id) {
  if (!confirm('ลบรายการนี้?')) return;
  state.income = state.income.filter(i => i.id !== id);
  save();
  renderIncome();
  renderDashboard();
  renderRecent();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg> ลบรายการเรียบร้อย');
}

// ----- Expense Form -----
document.getElementById('form-expense').addEventListener('submit', e => {
  e.preventDefault();
  const entry = {
    id: Date.now(),
    date: document.getElementById('expense-date').value,
    category: document.getElementById('expense-category').value,
    amount: parseFloat(document.getElementById('expense-amount').value) || 0,
    payment: document.getElementById('expense-payment').value,
    description: document.getElementById('expense-desc').value
  };
  state.expense.push(entry);
  save();
  renderExpense();
  renderDashboard();
  renderRecent();
  renderCategoryChart();
  e.target.reset();
  document.getElementById('expense-date').value = todayISO();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> บันทึกรายจ่ายเรียบร้อย');
});

function renderExpense() {
  const tbody = document.querySelector('#table-expense tbody');
  if (state.expense.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg></div>ยังไม่มีข้อมูลรายจ่าย</td></tr>';
    return;
  }
  tbody.innerHTML = [...state.expense].reverse().map(i => `
    <tr>
      <td>${i.date}</td>
      <td><span class="badge">${i.category}</span></td>
      <td>${escapeHtml(i.description)}</td>
      <td class="amount-expense">${fmt(i.amount)}</td>
      <td class="text-dim small">${i.payment}</td>
      <td><button class="btn btn-danger btn-small" onclick="deleteExpense(${i.id})"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button></td>
    </tr>
  `).join('');
}

function deleteExpense(id) {
  if (!confirm('ลบรายการนี้?')) return;
  state.expense = state.expense.filter(i => i.id !== id);
  save();
  renderExpense();
  renderDashboard();
  renderRecent();
  renderCategoryChart();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg> ลบรายการเรียบร้อย');
}

// ----- Goals Form -----
document.getElementById('form-goal').addEventListener('submit', e => {
  e.preventDefault();
  const entry = {
    id: Date.now(),
    name: document.getElementById('goal-name').value,
    target: parseFloat(document.getElementById('goal-target').value) || 0,
    current: parseFloat(document.getElementById('goal-current').value) || 0,
    monthly: parseFloat(document.getElementById('goal-monthly').value) || 0
  };
  state.goals.push(entry);
  save();
  renderGoals();
  e.target.reset();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> เพิ่มเป้าหมายเรียบร้อย');
});

function renderGoals() {
  const container = document.getElementById('goals-list');
  if (state.goals.length === 0) {
    container.innerHTML = '<div class="empty"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg></div>ยังไม่มีเป้าหมาย — เพิ่มเป้าหมายแรกของคุณด้านบน</div>';
    return;
  }
  container.innerHTML = state.goals.map(g => {
    const pct = g.target > 0 ? Math.min(100, (g.current / g.target) * 100) : 0;
    const remaining = Math.max(0, g.target - g.current);
    const eta = g.monthly > 0 ? Math.ceil(remaining / g.monthly) : null;
    const fillClass = pct >= 100 ? 'success' : pct >= 50 ? '' : pct >= 25 ? 'warning' : 'danger';
    return `<div class="goal-card">
      <div class="goal-header">
        <div>
          <div class="goal-name">${escapeHtml(g.name)} ${pct >= 100 ? '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>' : ''}</div>
          <div class="text-dim small">${fmt(g.current)} / ${fmt(g.target)} (${pct.toFixed(1)}%)</div>
        </div>
        <button class="btn btn-danger btn-small" onclick="deleteGoal(${g.id})"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button>
      </div>
      <div class="progress">
        <div class="progress-fill ${fillClass}" style="width: ${pct}%">${pct.toFixed(0)}%</div>
      </div>
      <div class="text-dim small mt-2">
        เหลืออีก: <strong class="text-warning">${fmt(remaining)}</strong> บาท
        ${eta ? ` · คาดว่าถึงเป้าใน <strong>${eta} เดือน</strong>` : ''}
        ${g.monthly > 0 ? ` · ออมเดือนละ ${fmt(g.monthly)} บาท` : ''}
      </div>
    </div>`;
  }).join('');
}

function deleteGoal(id) {
  if (!confirm('ลบเป้าหมายนี้?')) return;
  state.goals = state.goals.filter(g => g.id !== id);
  save();
  renderGoals();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg> ลบเป้าหมายเรียบร้อย');
}

// ----- Dashboard -----
function renderDashboard() {
  const now = new Date();
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  
  const monthIncome = state.income
    .filter(i => new Date(i.date) >= monthStart && new Date(i.date) <= monthEnd)
    .reduce((s, i) => s + i.gross, 0);
  const monthExpense = state.expense
    .filter(i => new Date(i.date) >= monthStart && new Date(i.date) <= monthEnd)
    .reduce((s, i) => s + i.amount, 0);
  const balance = monthIncome - monthExpense;
  const incomeCount = state.income.filter(i => new Date(i.date) >= monthStart && new Date(i.date) <= monthEnd).length;
  const expenseCount = state.expense.filter(i => new Date(i.date) >= monthStart && new Date(i.date) <= monthEnd).length;
  
  document.getElementById('stat-income').textContent = fmt(monthIncome);
  document.getElementById('stat-expense').textContent = fmt(monthExpense);
  document.getElementById('stat-balance').textContent = fmt(balance);
  document.getElementById('stat-income-count').textContent = incomeCount + ' รายการ';
  document.getElementById('stat-expense-count').textContent = expenseCount + ' รายการ';
  const savingsRate = monthIncome > 0 ? (balance / monthIncome * 100).toFixed(1) : 0;
  const savingsEl = document.getElementById('stat-savings-rate');
  savingsEl.textContent = `ออม ${savingsRate}%`;
  savingsEl.className = savingsRate >= state.settings.savingsTargetPct ? 'text-success' : 'text-warning';
  
  // Tax estimate
  const annualIncome = monthIncome * 12;
  const annualExpense = monthExpense * 12;
  const annualNet = Math.max(0, annualIncome - state.settings.personalAllowance - 9000);
  const estTax = calcTax(annualNet);
  document.getElementById('stat-tax').textContent = fmt(estTax);
  
  // Auto-fill tax form
  const ytdIncome = state.income
    .filter(i => new Date(i.date) <= now)
    .reduce((s, i) => s + i.gross, 0);
  const ytdWithheld = state.income
    .filter(i => new Date(i.date) <= now)
    .reduce((s, i) => s + i.tax, 0);
  
  document.getElementById('tax-gross').value = ytdIncome || annualIncome;
  document.getElementById('tax-withheld').value = ytdWithheld;
  recalcTax();
  
  renderTrendChart();
}

function renderRecent() {
  const all = [
    ...state.income.map(i => ({ ...i, type: 'income', category: i.type })),
    ...state.expense.map(i => ({ ...i, type: 'expense', amount: i.amount, description: i.description }))
  ].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 10);
  
  const tbody = document.querySelector('#table-recent tbody');
  if (all.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty"><div class="empty-icon"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg></div>ยังไม่มีธุรกรรม</td></tr>';
    return;
  }
  tbody.innerHTML = all.map(t => `
    <tr>
      <td>${t.date}</td>
      <td><span class="badge">${t.type === 'income' ? '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายรับ' : '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg> รายจ่าย'}</span></td>
      <td>${t.category}</td>
      <td>${escapeHtml(t.description || t.source || t.notes || '-')}</td>
      <td class="${t.type === 'income' ? 'amount-income' : 'amount-expense'}">
        ${t.type === 'income' ? '+' : '-'}${fmt(t.type === 'income' ? t.gross : t.amount)}
      </td>
      <td>
        <button class="btn btn-danger btn-small" onclick="deleteTransaction('${t.type}', ${t.id})"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></button>
      </td>
    </tr>
  `).join('');
}

function deleteTransaction(type, id) {
  if (type === 'income') deleteIncome(id);
  else deleteExpense(id);
}

// ----- Charts (Inline SVG) -----
function renderTrendChart() {
  const container = document.getElementById('chart-trend');
  const months = [];
  const now = new Date();
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const end = new Date(now.getFullYear(), now.getMonth() - i + 1, 0);
    const income = state.income
      .filter(x => new Date(x.date) >= d && new Date(x.date) <= end)
      .reduce((s, x) => s + x.gross, 0);
    const expense = state.expense
      .filter(x => new Date(x.date) >= d && new Date(x.date) <= end)
      .reduce((s, x) => s + x.amount, 0);
    months.push({ label: d.toLocaleDateString('th-TH', { month: 'short' }), income, expense });
  }
  
  const W = container.clientWidth - 24, H = 240, P = 30;
  const max = Math.max(...months.map(m => Math.max(m.income, m.expense)), 1);
  const barW = (W - P * 2) / months.length / 2.4;
  
  let svg = `<svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}">`;
  // Grid lines
  for (let i = 0; i <= 4; i++) {
    const y = P + (H - P * 2) * (i / 4);
    svg += `<line x1="${P}" y1="${y}" x2="${W - P}" y2="${y}" stroke="#475569" stroke-dasharray="2,2"/>`;
    svg += `<text x="5" y="${y + 3}" fill="#94a3b8" font-size="10">${fmtNum(max * (1 - i / 4))}</text>`;
  }
  // Bars
  months.forEach((m, idx) => {
    const x = P + (W - P * 2) * idx / months.length;
    const iH = (m.income / max) * (H - P * 2);
    const eH = (m.expense / max) * (H - P * 2);
    svg += `<rect x="${x + 2}" y="${H - P - iH}" width="${barW}" height="${iH}" fill="#22c55e" opacity="0.85" rx="2"/>`;
    svg += `<rect x="${x + barW + 4}" y="${H - P - eH}" width="${barW}" height="${eH}" fill="#ef4444" opacity="0.85" rx="2"/>`;
    svg += `<text x="${x + barW + 3}" y="${H - 8}" fill="#94a3b8" font-size="10" text-anchor="middle">${m.label}</text>`;
  });
  // Legend
  svg += `<rect x="${W - 130}" y="8" width="10" height="10" fill="#22c55e" rx="2"/><text x="${W - 116}" y="17" fill="#f1f5f9" font-size="11">รายรับ</text>`;
  svg += `<rect x="${W - 70}" y="8" width="10" height="10" fill="#ef4444" rx="2"/><text x="${W - 56}" y="17" fill="#f1f5f9" font-size="11">รายจ่าย</text>`;
  svg += `</svg>`;
  container.innerHTML = svg;
}

function renderCategoryChart() {
  const container = document.getElementById('chart-category');
  const byCat = {};
  state.expense.forEach(e => { byCat[e.category] = (byCat[e.category] || 0) + e.amount; });
  const total = Object.values(byCat).reduce((s, v) => s + v, 0);
  if (total === 0) {
    container.innerHTML = '<div class="empty">ยังไม่มีข้อมูลรายจ่าย</div>';
    return;
  }
  const cats = Object.entries(byCat).sort((a, b) => b[1] - a[1]);
  const W = container.clientWidth - 24, H = 240;
  const colors = ['#3b82f6', '#22c55e', '#ef4444', '#f59e0b', '#a855f7', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#6366f1'];
  
  let svg = `<svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}">`;
  let cumPct = 0;
  const cx = W * 0.3, cy = H / 2, r = 80, ir = 50;
  
  cats.forEach(([cat, val], idx) => {
    const pct = val / total;
    const startAngle = cumPct * Math.PI * 2;
    const endAngle = (cumPct + pct) * Math.PI * 2;
    cumPct += pct;
    
    const x1 = cx + Math.cos(startAngle) * r;
    const y1 = cy + Math.sin(startAngle) * r;
    const x2 = cx + Math.cos(endAngle) * r;
    const y2 = cy + Math.sin(endAngle) * r;
    const x3 = cx + Math.cos(endAngle) * ir;
    const y3 = cy + Math.sin(endAngle) * ir;
    const x4 = cx + Math.cos(startAngle) * ir;
    const y4 = cy + Math.sin(startAngle) * ir;
    
    const largeArc = pct > 0.5 ? 1 : 0;
    const path = `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${ir} ${ir} 0 ${largeArc} 0 ${x4} ${y4} Z`;
    svg += `<path d="${path}" fill="${colors[idx % colors.length]}" opacity="0.9"/>`;
  });
  
  svg += `<text x="${cx}" y="${cy - 5}" fill="#f1f5f9" font-size="14" text-anchor="middle" font-weight="600">${fmt(total)}</text>`;
  svg += `<text x="${cx}" y="${cy + 12}" fill="#94a3b8" font-size="11" text-anchor="middle">รวม</text>`;
  
  // Legend
  let lx = W * 0.55, ly = 20;
  cats.slice(0, 8).forEach(([cat, val], idx) => {
    const pct = (val / total * 100).toFixed(1);
    svg += `<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="${colors[idx % colors.length]}" rx="2"/>`;
    svg += `<text x="${lx + 16}" y="${ly}" fill="#f1f5f9" font-size="11">${cat} (${pct}%)</text>`;
    ly += 18;
  });
  svg += `</svg>`;
  container.innerHTML = svg;
}

// ----- Settings -----
function saveSettings() {
  state.settings.monthlyBudget = parseFloat(document.getElementById('set-budget').value) || 20000;
  state.settings.savingsTargetPct = parseFloat(document.getElementById('set-savings-target').value) || 20;
  state.settings.personalAllowance = parseFloat(document.getElementById('set-allowance').value) || 60000;
  save();
  renderDashboard();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> บันทึกการตั้งค่าเรียบร้อย');
}

function loadSettings() {
  document.getElementById('set-budget').value = state.settings.monthlyBudget;
  document.getElementById('set-savings-target').value = state.settings.savingsTargetPct;
  document.getElementById('set-allowance').value = state.settings.personalAllowance;
}

// ----- Import / Export -----
function exportCSV() {
  let csv = 'Type,Date,Category,Description,Amount,Payment,Notes\n';
  state.income.forEach(i => {
    csv += `Income,${i.date},"${i.source}","${i.type}",${i.gross},"","Tax: ${i.tax} | ${i.notes || ''}"\n`;
  });
  state.expense.forEach(e => {
    csv += `Expense,${e.date},"${e.category}","${e.description}",${e.amount},"${e.payment}","${e.notes || ''}"\n`;
  });
  download(csv, `finance-${todayISO()}.csv`, 'text/csv;charset=utf-8;');
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Export CSV เรียบร้อย');
}

function exportJSON() {
  const json = JSON.stringify(state, null, 2);
  download(json, `finance-${todayISO()}.json`, 'application/json');
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> Export JSON เรียบร้อย');
}

function importJSON(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      const data = JSON.parse(ev.target.result);
      if (confirm('Import จะแทนที่ข้อมูลเดิม ตกลงไหม?')) {
        state = { ...state, ...data, settings: { ...state.settings, ...(data.settings || {}) } };
        save();
        renderAll();
        toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> Import สำเร็จ');
      }
    } catch (err) {
      toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg> ไฟล์ไม่ถูกต้อง', 'error');
    }
  };
  reader.readAsText(file);
}

function clearAllData() {
  if (!confirm('ลบข้อมูลทั้งหมด? การกระทำนี้ไม่สามารถ undo ได้')) return;
  if (!confirm('ยืนยันอีกครั้ง — ลบจริง ๆ ใช่ไหม?')) return;
  state = { income: [], expense: [], goals: [], settings: state.settings };
  save();
  renderAll();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg> ลบข้อมูลทั้งหมดแล้ว', 'warning');
}

function loadSampleData() {
  if (state.income.length > 0 || state.expense.length > 0) {
    if (!confirm('มีข้อมูลอยู่แล้ว ต้องการเพิ่มข้อมูลตัวอย่าง (ไม่ลบของเดิม)?')) return;
  }
  const sampleIncome = [
    { id: Date.now() + 1, date: '2026-06-01', source: 'บริษัท ABC', type: 'Salary', gross: 35000, tax: 1500, net: 33500, notes: 'เงินเดือน' },
    { id: Date.now() + 2, date: '2026-06-15', source: 'บริษัท ABC', type: 'Salary', gross: 35000, tax: 1500, net: 33500, notes: 'เงินเดือน' },
    { id: Date.now() + 3, date: '2026-06-10', source: 'ลูกค้า XYZ', type: 'Freelance', gross: 15000, tax: 750, net: 14250, notes: 'ทำเว็บ' }
  ];
  const sampleExpense = [
    { id: Date.now() + 11, date: '2026-06-01', category: 'Housing', amount: 8000, payment: 'Bank Transfer', description: 'ค่าเช่าห้อง' },
    { id: Date.now() + 12, date: '2026-06-02', category: 'Food', amount: 850, payment: 'PromptPay', description: 'กับข้าว + ของสด' },
    { id: Date.now() + 13, date: '2026-06-03', category: 'Transport', amount: 1200, payment: 'Credit Card', description: 'น้ำมันรถ' },
    { id: Date.now() + 14, date: '2026-06-05', category: 'Entertainment', amount: 419, payment: 'Credit Card', description: 'Netflix' },
    { id: Date.now() + 15, date: '2026-06-07', category: 'Shopping', amount: 1500, payment: 'PromptPay', description: 'เสื้อผ้า UNIQLO' },
    { id: Date.now() + 16, date: '2026-06-08', category: 'Transport', amount: 1000, payment: 'PromptPay', description: 'BTS เดือน' },
    { id: Date.now() + 17, date: '2026-06-09', category: 'Education', amount: 750, payment: 'Credit Card', description: 'ซื้อหนังสือ' }
  ];
  const sampleGoals = [
    { id: Date.now() + 21, name: 'Emergency Fund', target: 100000, current: 45000, monthly: 5000 },
    { id: Date.now() + 22, name: 'Japan Trip', target: 80000, current: 20000, monthly: 10000 },
    { id: Date.now() + 23, name: 'New Laptop', target: 50000, current: 50000, monthly: 0 }
  ];
  state.income.push(...sampleIncome);
  state.expense.push(...sampleExpense);
  state.goals.push(...sampleGoals);
  save();
  renderAll();
  toast('<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> โหลดข้อมูลตัวอย่างเรียบร้อย');
}

function download(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----- Toast -----
function toast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ----- Language toggle -----
function toggleLang() {
  state.settings.language = state.settings.language === 'th' ? 'en' : 'th';
  save();
  applyLang();
}

function applyLang() {
  const lang = state.settings.language;
  document.querySelectorAll('[data-' + lang + ']').forEach(el => {
    el.textContent = el.dataset[lang];
  });
}

// ----- Utility -----
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ----- Render all -----
function renderAll() {
  renderDashboard();
  renderIncome();
  renderExpense();
  renderGoals();
  renderRecent();
  renderCategoryChart();
  loadSettings();
  applyLang();
}

// ----- Init -----
window.addEventListener('DOMContentLoaded', () => {
  load();
  document.getElementById('income-date').value = todayISO();
  document.getElementById('expense-date').value = todayISO();
  renderAll();
  
  window.addEventListener('resize', () => {
    renderTrendChart();
    renderCategoryChart();
  });
});
</script>
</body>
</html>
```
