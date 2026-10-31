# freelance-pricing-calculator delivery bundle

This bundle contains the original AI Factory delivery assets.
Source files are preserved below with their relative paths.

## Source: `downloads/03-freelance-pricing-calculator.html`

```html
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>เครื่องคำนวณราคา Freelance | Ai Factory Pricing Calculator</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Sarabun', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; color: #1a202c; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { text-align: center; color: white; padding: 30px 0; }
    .header h1 { font-size: 2.2em; margin-bottom: 8px; }
    .header p { opacity: 0.95; font-size: 1.05em; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 20px; }
    @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
    .card { background: white; border-radius: 16px; padding: 28px; box-shadow: 0 20px 60px rgba(0,0,0,0.15); }
    .card h2 { font-size: 1.3em; margin-bottom: 18px; color: #2d3748; border-bottom: 2px solid #edf2f7; padding-bottom: 10px; }
    .field { margin-bottom: 16px; }
    .field label { display: block; font-size: 0.92em; font-weight: 600; margin-bottom: 6px; color: #4a5568; }
    .field label small { font-weight: 400; color: #718096; }
    .field input, .field select { width: 100%; padding: 11px 14px; border: 2px solid #e2e8f0; border-radius: 8px; font-size: 1em; transition: border 0.2s; }
    .field input:focus, .field select:focus { outline: none; border-color: #667eea; }
    .field .hint { font-size: 0.8em; color: #718096; margin-top: 4px; }
    .results { background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%); }
    .tier { background: white; border-radius: 12px; padding: 20px; margin-bottom: 14px; border-left: 4px solid #667eea; }
    .tier-label { font-size: 0.85em; text-transform: uppercase; letter-spacing: 1px; color: #718096; margin-bottom: 6px; }
    .tier-price { font-size: 1.9em; font-weight: 700; color: #2d3748; }
    .tier-price small { font-size: 0.45em; color: #718096; font-weight: 500; }
    .tier-desc { font-size: 0.88em; color: #4a5568; margin-top: 6px; }
    .row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #e2e8f0; font-size: 0.92em; }
    .row:last-child { border: none; }
    .row .label { color: #4a5568; }
    .row .value { font-weight: 600; color: #2d3748; }
    .btn-row { display: flex; gap: 10px; margin-top: 18px; }
    .btn { flex: 1; padding: 12px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 0.95em; transition: transform 0.1s, box-shadow 0.1s; }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .btn-primary { background: #667eea; color: white; }
    .btn-secondary { background: #e2e8f0; color: #2d3748; }
    .market-table { width: 100%; border-collapse: collapse; font-size: 0.9em; margin-top: 14px; }
    .market-table th, .market-table td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #edf2f7; }
    .market-table th { background: #f7fafc; font-weight: 600; color: #4a5568; font-size: 0.85em; text-transform: uppercase; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; }
    .badge-junior { background: #fef3c7; color: #92400e; }
    .badge-mid { background: #dbeafe; color: #1e40af; }
    .badge-senior { background: #ede9fe; color: #5b21b6; }
    .utilization { background: #f7fafc; border-radius: 8px; padding: 14px; margin-top: 14px; }
    .util-row { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; font-size: 0.92em; }
    .util-row .price { font-weight: 700; color: #667eea; }
    .toast { position: fixed; bottom: 20px; right: 20px; background: #2d3748; color: white; padding: 14px 22px; border-radius: 8px; opacity: 0; transform: translateY(20px); transition: all 0.3s; }
    .toast.show { opacity: 1; transform: translateY(0); }
    .footer { text-align: center; color: white; padding: 24px; font-size: 0.88em; opacity: 0.85; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"/></svg> เครื่องคำนวณราคา Freelance</h1>
      <p>คำนวณราคา 3 ระดับ (รายชั่วโมง / รายวัน / รายโปรเจกต์) ตามต้นทุนจริง + เปรียบเทียบกับตลาด TH 2026</p>
    </div>

    <div class="grid">
      <!-- INPUTS -->
      <div class="card">
        <h2><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ข้อมูลของคุณ</h2>

        <div class="field">
          <label>ต้นทุนชีวิตต่อเดือน (THB)</label>
          <input type="number" id="cost" value="40000" min="0">
          <div class="hint">ค่าเช่า + อาหาร + ประกัน + เงินออม + ภาระทั้งหมด/เดือน</div>
        </div>

        <div class="field">
          <label>ชั่วโมงทำงานจริงต่อเดือน (Billable hours)</label>
          <input type="number" id="hours" value="120" min="1">
          <div class="hint">แนะนำ 100-140 ชม. (จาก 22 วันทำงาน × 5-7 ชม./วัน)</div>
        </div>

        <div class="field">
          <label>อัตรากำไรที่ต้องการ (%)</label>
          <input type="number" id="margin" value="30" min="0" max="100">
          <div class="hint">Freelance ทั่วไป: 20-40% · Senior: 40-60%</div>
        </div>

        <div class="field">
          <label>สำรองภาษี + ประกันสังคม (%)</label>
          <input type="number" id="tax" value="15" min="0" max="50">
          <div class="hint">ภาษีเงินได้บุคคลธรรมดา + ประกันสังคม ตามจริง</div>
        </div>

        <div class="field">
          <label>ชั่วโมง Overhead ต่อโปรเจกต์ (ชม.)</label>
          <input type="number" id="overhead" value="6" min="0">
          <div class="hint">เวลาประชุม + แก้ไข + ส่งงาน + เปิดบิล</div>
        </div>

        <div class="field">
          <label>ระดับประสบการณ์</label>
          <select id="level">
            <option value="junior">Junior (0-2 ปี)</option>
            <option value="mid" selected>Mid-level (3-5 ปี)</option>
            <option value="senior">Senior (6+ ปี)</option>
          </select>
          <div class="hint">ใช้เปรียบเทียบกับ market rate TH 2026</div>
        </div>

        <div class="btn-row">
          <button class="btn btn-secondary" onclick="resetForm()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg> รีเซ็ต</button>
          <button class="btn btn-primary" onclick="copyResults()"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg> คัดลอกผลลัพธ์</button>
        </div>
      </div>

      <!-- RESULTS -->
      <div class="card results">
        <h2><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.94s4.18 1.36 4.18 3.85c-.01 1.83-1.38 2.83-3.12 3.19z"/></svg> ราคาที่แนะนำ</h2>

        <div class="tier">
          <div class="tier-label">รายชั่วโมง (Hourly Rate)</div>
          <div class="tier-price" id="hourly">0 <small>THB / ชม.</small></div>
          <div class="tier-desc">เหมาะกับงาน retainer, support, maintenance</div>
        </div>

        <div class="tier">
          <div class="tier-label">รายวัน (Day Rate · 8 ชม.)</div>
          <div class="tier-price" id="daily">0 <small>THB / วัน</small></div>
          <div class="tier-desc">เหมาะกับ sprint, workshop, consulting</div>
        </div>

        <div class="tier">
          <div class="tier-label">รายโปรเจกต์ (Project Flat)</div>
          <div class="tier-price" id="project">0 <small>THB</small></div>
          <div class="tier-desc" id="projectScope">—</div>
        </div>

        <h2 style="margin-top: 24px;"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> รายละเอียดต้นทุน</h2>
        <div class="row"><span class="label">ต้นทุน/ชั่วโมง</span><span class="value" id="costPerHour">0 THB</span></div>
        <div class="row"><span class="label">+ กำไร</span><span class="value" id="profitPerHour">0 THB</span></div>
        <div class="row"><span class="label">+ ภาษี/ประกัน</span><span class="value" id="taxPerHour">0 THB</span></div>
        <div class="row"><span class="label">+ Overhead/ชม.</span><span class="value" id="overheadPerHour">0 THB</span></div>

        <h2 style="margin-top: 24px;"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2"/></svg> Break-even & Discount</h2>
        <div class="utilization">
          <div class="util-row"><span>Break-even (ชม.ขั้นต่ำ/เดือน)</span><span class="price" id="breakeven">0 ชม.</span></div>
          <div class="util-row"><span>ราคาที่ Utilization 60%</span><span class="price" id="u60">0 THB/ชม.</span></div>
          <div class="util-row"><span>ราคาที่ Utilization 40%</span><span class="price" id="u40">0 THB/ชม.</span></div>
          <div class="util-row"><span>ราคาที่ Utilization 20%</span><span class="price" id="u20">0 THB/ชม.</span></div>
        </div>

        <h2 style="margin-top: 24px;"><svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6h-6z"/></svg> เทียบกับตลาด TH 2026</h2>
        <table class="market-table">
          <thead><tr><th>ระดับ</th><th>ช่วงราคา</th><th>คุณอยู่ที่</th></tr></thead>
          <tbody>
            <tr><td><span class="badge badge-junior">Junior</span></td><td>500-1,500 THB/ชม.</td><td id="vs-junior">—</td></tr>
            <tr><td><span class="badge badge-mid">Mid</span></td><td>1,500-3,000 THB/ชม.</td><td id="vs-mid">—</td></tr>
            <tr><td><span class="badge badge-senior">Senior</span></td><td>3,000-6,000 THB/ชม.</td><td id="vs-senior">—</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="footer">
      © 2026 Ai Factory · <a href="mailto:hello@aifactory.co" style="color:white;">hello@aifactory.co</a> · Updated 2026-06-05
    </div>
  </div>

  <div class="toast" id="toast">คัดลอกเรียบร้อย!</div>

  <script>
    const THB = v => new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', maximumFractionDigits: 0 }).format(v);
    const inputs = ['cost', 'hours', 'margin', 'tax', 'overhead', 'level'].map(id => document.getElementById(id));

    function calculate() {
      const cost = +document.getElementById('cost').value;
      const hours = +document.getElementById('hours').value;
      const margin = +document.getElementById('margin').value;
      const tax = +document.getElementById('tax').value;
      const overhead = +document.getElementById('overhead').value;
      const level = document.getElementById('level').value;

      if (!cost || !hours) return;

      const costPerHour = cost / hours;
      const profitPerHour = costPerHour * (margin / 100);
      const taxPerHour = costPerHour * (tax / 100);
      const overheadPerHour = overhead * 0.05 * costPerHour; // distribute overhead
      const hourlyRate = costPerHour + profitPerHour + taxPerHour + overheadPerHour;
      const dailyRate = hourlyRate * 8;
      const projectRate = dailyRate * 5 + (overhead * hourlyRate); // 5 working days + overhead

      document.getElementById('hourly').innerHTML = THB(hourlyRate) + ' <small>THB / ชม.</small>';
      document.getElementById('daily').innerHTML = THB(dailyRate) + ' <small>THB / วัน</small>';
      document.getElementById('project').innerHTML = THB(projectRate) + ' <small>THB</small>';
      document.getElementById('projectScope').textContent = `~5 วันทำงาน + ${overhead} ชม. overhead`;

      document.getElementById('costPerHour').textContent = THB(costPerHour);
      document.getElementById('profitPerHour').textContent = THB(profitPerHour);
      document.getElementById('taxPerHour').textContent = THB(taxPerHour);
      document.getElementById('overheadPerHour').textContent = THB(overheadPerHour);

      // Break-even
      const breakeven = Math.ceil(cost / (hourlyRate * (1 - tax/100)));
      document.getElementById('breakeven').textContent = breakeven + ' ชม.';

      // Utilization-based pricing
      const u60 = (cost / (hours * 0.6)) * (1 + margin/100) * (1 + tax/100);
      const u40 = (cost / (hours * 0.4)) * (1 + margin/100) * (1 + tax/100);
      const u20 = (cost / (hours * 0.2)) * (1 + margin/100) * (1 + tax/100);
      document.getElementById('u60').textContent = THB(u60) + '/ชม.';
      document.getElementById('u40').textContent = THB(u40) + '/ชม.';
      document.getElementById('u20').textContent = THB(u20) + '/ชม.';

      // Market comparison
      const compare = (rate, min, max) => {
        if (rate < min) return `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M11 4v12.17l-3.59-3.58L6 14l6 6 6-6-1.41-1.41L13 16.17V4h-2z"/></svg> ต่ำกว่าตลาด ${Math.round((1 - rate/min)*100)}%`;
        if (rate > max) return `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8-8-8z"/></svg> สูงกว่าตลาด ${Math.round((rate/max - 1)*100)}%`;
        return `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> อยู่ในช่วง`;
      };
      document.getElementById('vs-junior').textContent = compare(hourlyRate, 500, 1500);
      document.getElementById('vs-mid').textContent = compare(hourlyRate, 1500, 3000);
      document.getElementById('vs-senior').textContent = compare(hourlyRate, 3000, 6000);
    }

    function resetForm() {
      document.getElementById('cost').value = 40000;
      document.getElementById('hours').value = 120;
      document.getElementById('margin').value = 30;
      document.getElementById('tax').value = 15;
      document.getElementById('overhead').value = 6;
      document.getElementById('level').value = 'mid';
      calculate();
    }

    function copyResults() {
      const hourly = document.getElementById('hourly').innerText;
      const daily = document.getElementById('daily').innerText;
      const project = document.getElementById('project').innerText;
      const text = `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg> Pricing Recommendation\n\n<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"/></svg> Hourly: ${hourly}\n<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM9 10H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2z"/></svg> Daily: ${daily}\n<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle"><path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/></svg> Project: ${project}\n\nGenerated: 2026-06-05`;
      navigator.clipboard.writeText(text).then(() => {
        const toast = document.getElementById('toast');
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 2000);
      });
    }

    inputs.forEach(el => el.addEventListener('input', calculate));
    calculate();
  </script>
</body>
</html>
```
