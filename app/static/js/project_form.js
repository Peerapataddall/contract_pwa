(function(){
  const fmt2 = (n) => {
    const x = Number(n || 0);
    return x.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  };

  const val = (el) => (el ? el.value : '');
  const num = (v) => {
    const x = parseFloat(String(v).replace(/,/g,''));
    return Number.isFinite(x) ? x : 0;
  };

  const byId = (id) => document.getElementById(id);

  function rowRemove(btn){
    const tr = btn.closest('tr');
    if (tr) tr.remove();
    ProjectForm.recalc();
  }

  function makeInput(placeholder, value, cls='input input-table', type='text'){
    const input = document.createElement('input');
    input.type = type;
    input.className = cls;
    input.placeholder = placeholder;
    input.value = (value === null || value === undefined) ? '' : value;

    // ✅ date input ใช้ change จะชัวร์กว่า (บาง browser ไม่ยิง input ทุกครั้ง)
    const evt = (type === 'date') ? 'change' : 'input';
    input.addEventListener(evt, () => ProjectForm.recalc());
    input.addEventListener('input', () => ProjectForm.recalc());

    return input;
  }

  function makeButton(text, cls){
    const b = document.createElement('button');
    b.type='button';
    b.className = cls;
    b.textContent = text;
    return b;
  }

  const Materials = {
    tbody(){ return byId('materials_table')?.querySelector('tbody'); },
    addRow(data={}){
      const tr = document.createElement('tr');

      const tdBrand = document.createElement('td');
      tdBrand.appendChild(makeInput('ยี่ห้อ', data.brand));

      const tdCode = document.createElement('td');
      tdCode.appendChild(makeInput('รหัส', data.item_code, 'input input-table mono'));

      const tdName = document.createElement('td');
      tdName.appendChild(makeInput('ชื่อวัสดุ', data.item_name));

      // ✅ NEW: ใบกำกับเลขที่
      const tdInvNo = document.createElement('td');
      tdInvNo.appendChild(makeInput('เช่น INV-000123', data.tax_invoice_no, 'input input-table mono'));

      // ✅ NEW: วันที่ใบกำกับ (ปฏิทิน)
      const tdInvDate = document.createElement('td');
      tdInvDate.appendChild(makeInput('', data.tax_invoice_date, 'input input-table mono', 'date'));

      const tdUP = document.createElement('td'); tdUP.className='right';
      tdUP.appendChild(makeInput('0.00', data.unit_price, 'input input-table right mono', 'number'));

      const tdQty = document.createElement('td'); tdQty.className='right';
      tdQty.appendChild(makeInput('0.00', data.qty, 'input input-table right mono', 'number'));

      const tdTotal = document.createElement('td'); tdTotal.className='right mono';
      tdTotal.textContent = '0.00';

      const tdDel = document.createElement('td'); tdDel.className='right';
      const del = makeButton('✖','btn btn-small btn-ghost');
      del.addEventListener('click', ()=>rowRemove(del));
      tdDel.appendChild(del);

      // ✅ ต้องเรียงให้ตรงกับ THEAD
      tr.append(tdBrand, tdCode, tdName, tdInvNo, tdInvDate, tdUP, tdQty, tdTotal, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },
    read(){
      const rows = [];
      this.tbody()?.querySelectorAll('tr').forEach(tr=>{
        const tds = tr.querySelectorAll('td');

        // indexes ตาม THEAD:
        // 0 brand, 1 code, 2 name, 3 inv_no, 4 inv_date, 5 unit_price, 6 qty, 7 total, 8 del
        const brand = val(tds[0].querySelector('input'));
        const item_code = val(tds[1].querySelector('input'));
        const item_name = val(tds[2].querySelector('input'));
        const tax_invoice_no = val(tds[3].querySelector('input'));
        const tax_invoice_date = val(tds[4].querySelector('input')); // YYYY-MM-DD จาก date picker
        const unit_price = num(val(tds[5].querySelector('input')));
        const qty = num(val(tds[6].querySelector('input')));

        const total = unit_price * qty;
        tds[7].textContent = fmt2(total);

        rows.push({brand, item_code, item_name, tax_invoice_no, tax_invoice_date, unit_price, qty});
      });
      return rows;
    }
  };

  const Subs = {
    tbody(){ return byId('subs_table')?.querySelector('tbody'); },
    addRow(data={}){
      const tr = document.createElement('tr');

      const tdName = document.createElement('td');
      tdName.appendChild(makeInput('ชื่อผู้รับเหมาช่วง', data.vendor_name));

      const tdDate = document.createElement('td');
      tdDate.appendChild(makeInput('', data.pay_date, 'input input-table mono', 'date'));

      const tdAmt = document.createElement('td'); tdAmt.className='right';
      tdAmt.appendChild(makeInput('0.00', data.contract_amount, 'input input-table right mono', 'number'));

      const tdRate = document.createElement('td'); tdRate.className='right';
      tdRate.appendChild(makeInput('0', data.withholding_rate, 'input input-table right mono', 'number'));

      const tdWht = document.createElement('td'); tdWht.className='right';
      tdWht.appendChild(makeInput('0.00', data.withholding_amount, 'input input-table right mono', 'number'));

      const tdPay = document.createElement('td'); tdPay.className='right mono';
      tdPay.textContent = '0.00';

      const tdDel = document.createElement('td'); tdDel.className='right';
      const del = makeButton('✖','btn btn-small btn-ghost');
      del.addEventListener('click', ()=>rowRemove(del));
      tdDel.appendChild(del);

      const rateInput = tdRate.querySelector('input');
      const amtInput = tdAmt.querySelector('input');
      const whtInput = tdWht.querySelector('input');

      function autoWht(){
        const amt = num(val(amtInput));
        const rate = num(val(rateInput));
        const current = num(val(whtInput));
        if (rate > 0 && current === 0 && amt > 0) {
          whtInput.value = (amt * rate / 100).toFixed(2);
        }
      }
      rateInput.addEventListener('blur', autoWht);
      amtInput.addEventListener('blur', autoWht);

      tr.append(tdName, tdDate, tdAmt, tdRate, tdWht, tdPay, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },
    read(){
      const rows = [];
      this.tbody()?.querySelectorAll('tr').forEach(tr=>{
        const tds = tr.querySelectorAll('td');
        const vendor_name = val(tds[0].querySelector('input'));
        const pay_date = val(tds[1].querySelector('input'));
        const contract_amount = num(val(tds[2].querySelector('input')));
        const withholding_rate = num(val(tds[3].querySelector('input')));
        const withholding_amount = num(val(tds[4].querySelector('input')));
        const payable = Math.max(0, contract_amount - withholding_amount);
        tds[5].textContent = fmt2(payable);
        rows.push({vendor_name, pay_date, contract_amount, withholding_rate, withholding_amount});
      });
      return rows;
    }
  };

  const Expenses = {
    tbody(){ return byId('expenses_table')?.querySelector('tbody'); },
    addRow(data={}){
      const tr = document.createElement('tr');

      const tdCat = document.createElement('td');
      tdCat.appendChild(makeInput('เช่น น้ำมัน', data.category || 'อื่นๆ'));

      const tdTitle = document.createElement('td');
      tdTitle.appendChild(makeInput('รายการ', data.title));

      const tdDate = document.createElement('td');
      tdDate.appendChild(makeInput('', data.expense_date, 'input input-table mono', 'date'));

      const tdAmt = document.createElement('td'); tdAmt.className='right';
      tdAmt.appendChild(makeInput('0.00', data.amount, 'input input-table right mono', 'number'));

      const tdDel = document.createElement('td'); tdDel.className='right';
      const del = makeButton('✖','btn btn-small btn-ghost');
      del.addEventListener('click', ()=>rowRemove(del));
      tdDel.appendChild(del);

      tr.append(tdCat, tdTitle, tdDate, tdAmt, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },
    read(){
      const rows = [];
      this.tbody()?.querySelectorAll('tr').forEach(tr=>{
        const tds = tr.querySelectorAll('td');
        const category = val(tds[0].querySelector('input')) || 'อื่นๆ';
        const title = val(tds[1].querySelector('input'));
        const expense_date = val(tds[2].querySelector('input'));
        const amount = num(val(tds[3].querySelector('input')));
        rows.push({category, title, expense_date, amount});
      });
      return rows;
    }
  };

  const Advances = {
    tbody(){ return byId('advances_table')?.querySelector('tbody'); },
    addRow(data={}){
      const tr = document.createElement('tr');

      const tdTitle = document.createElement('td');
      tdTitle.appendChild(makeInput('รายการ', data.title));

      const tdDate = document.createElement('td');
      tdDate.appendChild(makeInput('', data.advance_date, 'input input-table mono', 'date'));

      const tdAmt = document.createElement('td'); tdAmt.className='right';
      tdAmt.appendChild(makeInput('0.00', data.amount, 'input input-table right mono', 'number'));

      const tdDel = document.createElement('td'); tdDel.className='right';
      const del = makeButton('✖','btn btn-small btn-ghost');
      del.addEventListener('click', ()=>rowRemove(del));
      tdDel.appendChild(del);

      tr.append(tdTitle, tdDate, tdAmt, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },
    read(){
      const rows = [];
      this.tbody()?.querySelectorAll('tr').forEach(tr=>{
        const tds = tr.querySelectorAll('td');
        const title = val(tds[0].querySelector('input'));
        const advance_date = val(tds[1].querySelector('input'));
        const amount = num(val(tds[2].querySelector('input')));
        rows.push({title, advance_date, amount});
      });
      return rows;
    }
  };

  const ProjectForm = {
    recalc(){
      const mats = Materials.read();
      const subs = Subs.read();
      const exps = Expenses.read();
      const advs = Advances.read();

      const mt = mats.reduce((a,r)=>a + (num(r.unit_price) * num(r.qty)), 0);
      const st = subs.reduce((a,r)=>a + Math.max(0, num(r.contract_amount) - num(r.withholding_amount)), 0);
      const et = exps.reduce((a,r)=>a + num(r.amount), 0);
      const at = advs.reduce((a,r)=>a + num(r.amount), 0);

      byId('materials_total').textContent = fmt2(mt);
      byId('subs_total').textContent = fmt2(st);
      byId('expenses_total').textContent = fmt2(et);
      byId('advances_total').textContent = fmt2(at);
      byId('grand_total').textContent = fmt2(mt + st + et + at);
    },

    collect(){
      return {
        code: val(byId('code')).trim(),
        name: val(byId('name')).trim(),
        description: val(byId('description')).trim(),
        customer_name: val(byId('customer_name')).trim(),
        location: val(byId('location')).trim(),
        start_date: val(byId('start_date')),
        end_date: val(byId('end_date')),
        work_days: num(val(byId('work_days'))),
        status: val(byId('status')),

        materials: Materials.read(),
        subcontractors: Subs.read(),
        expenses: Expenses.read(),
        advances: Advances.read(),
      };
    },

    async save(){
      const hint = byId('save_hint');
      hint.textContent = 'กำลังบันทึก...';

      const payload = this.collect();
      if (!payload.code) { hint.textContent = 'กรุณาใส่รหัสโครงการ'; byId('code').focus(); return; }
      if (!payload.name) { hint.textContent = 'กรุณาใส่ชื่อโครงการ'; byId('name').focus(); return; }

      const id = window.__PROJECT__ && window.__PROJECT__.id;
      const url = id ? `/api/projects/${id}` : '/api/projects';
      const method = id ? 'PUT' : 'POST';

      const resp = await fetch(url, {
        method,
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(()=>({ok:false,error:'บันทึกไม่สำเร็จ'}));
      if (!resp.ok || !data.ok){
        hint.textContent = data.error || 'บันทึกไม่สำเร็จ';
        return;
      }
      hint.textContent = 'บันทึกเรียบร้อย ✅';
      const pid = data.id;
      setTimeout(()=>{ window.location.href = `/projects/${pid}`; }, 450);
    },

    async remove(pid){
      if (!confirm('ต้องการลบโครงการนี้ใช่ไหม?')) return;
      const hint = byId('save_hint');
      hint.textContent = 'กำลังลบ...';
      const resp = await fetch(`/api/projects/${pid}`, {method:'DELETE'});
      const data = await resp.json().catch(()=>({ok:false}));
      if (!resp.ok || !data.ok){ hint.textContent = 'ลบไม่สำเร็จ'; return; }
      window.location.href = '/projects';
    }
  };

  window.Materials = Materials;
  window.Subs = Subs;
  window.Expenses = Expenses;
  window.Advances = Advances;
  window.ProjectForm = ProjectForm;

  const p = window.__PROJECT__ || {};
  (p.materials || []).forEach(r=>Materials.addRow(r));
  (p.subcontractors || []).forEach(r=>Subs.addRow(r));
  (p.expenses || []).forEach(r=>Expenses.addRow(r));
  (p.advances || []).forEach(r=>Advances.addRow(r));

  if ((p.materials || []).length === 0) Materials.addRow({});
  if ((p.subcontractors || []).length === 0) Subs.addRow({});
  if ((p.expenses || []).length === 0) Expenses.addRow({category:'อื่นๆ'});
  if ((p.advances || []).length === 0) Advances.addRow({});

  ProjectForm.recalc();
})();
