(function () {
  const fmt2 = (n) => {
    const x = Number(n || 0);
    return x.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const val = (el) => (el ? el.value : "");
  const byId = (id) => document.getElementById(id);

  const num = (v) => {
    const x = parseFloat(String(v ?? "").replace(/,/g, "").trim());
    return Number.isFinite(x) ? x : 0;
  };

  const clampNonNegative = (v) => {
    const n = num(v);
    return n < 0 ? 0 : n;
  };

  const allowedStatus = new Set(["IN_PROGRESS", "DEFECT", "DONE"]);

  function rowRemove(btn) {
    const tr = btn.closest("tr");
    if (tr) tr.remove();
    ProjectForm.recalc();
  }

  function makeInput(placeholder, value, cls = "input input-table", type = "text") {
    const input = document.createElement("input");
    input.type = type;
    input.className = cls;
    input.placeholder = placeholder;
    input.value = value === null || value === undefined ? "" : value;

    const evt = type === "date" ? "change" : "input";
    input.addEventListener(evt, () => ProjectForm.recalc());
    input.addEventListener("input", () => ProjectForm.recalc());

    if (type === "number") {
      input.min = "0";
      input.step = "0.01";
      input.addEventListener("blur", () => {
        const v = clampNonNegative(input.value);
        input.value = String(v);
        ProjectForm.recalc();
      });
    }

    return input;
  }

  function makeButton(text, cls) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = text;
    return b;
  }

  function readDateValue(id) {
    return (val(byId(id)) || "").trim();
  }

  function parseDateStr(s) {
    const t = String(s || "").trim();
    if (!t) return null;
    const d = new Date(`${t}T00:00:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  const Materials = {
    tbody() {
      return byId("materials_table")?.querySelector("tbody");
    },

    addRow(data = {}) {
      const tr = document.createElement("tr");

      const tdBrand = document.createElement("td");
      tdBrand.appendChild(makeInput("ยี่ห้อ", data.brand));

      const tdCode = document.createElement("td");
      tdCode.appendChild(makeInput("รหัส", data.item_code, "input input-table mono"));

      const tdName = document.createElement("td");
      tdName.appendChild(makeInput("ชื่อวัสดุ", data.item_name));

      const tdInvNo = document.createElement("td");
      tdInvNo.appendChild(makeInput("เช่น INV-000123", data.tax_invoice_no, "input input-table mono"));

      const tdInvDate = document.createElement("td");
      tdInvDate.appendChild(makeInput("", data.tax_invoice_date, "input input-table mono", "date"));

      const tdUP = document.createElement("td");
      tdUP.className = "right";
      tdUP.appendChild(makeInput("0.00", data.unit_price, "input input-table right mono", "number"));

      const tdQty = document.createElement("td");
      tdQty.className = "right";
      tdQty.appendChild(makeInput("0.00", data.qty, "input input-table right mono", "number"));

      const tdTotal = document.createElement("td");
      tdTotal.className = "right mono";
      tdTotal.textContent = "0.00";

      const tdDel = document.createElement("td");
      tdDel.className = "right";
      const del = makeButton("ลบ", "btn btn-small btn-ghost");
      del.addEventListener("click", () => rowRemove(del));
      tdDel.appendChild(del);

      tr.append(tdBrand, tdCode, tdName, tdInvNo, tdInvDate, tdUP, tdQty, tdTotal, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },

    read() {
      const rows = [];
      this.tbody()?.querySelectorAll("tr").forEach((tr) => {
        const tds = tr.querySelectorAll("td");

        const brand = val(tds[0].querySelector("input")).trim();
        const item_code = val(tds[1].querySelector("input")).trim();
        const item_name = val(tds[2].querySelector("input")).trim();
        const tax_invoice_no = val(tds[3].querySelector("input")).trim();
        const tax_invoice_date = val(tds[4].querySelector("input")).trim();
        const unit_price = clampNonNegative(val(tds[5].querySelector("input")));
        const qty = clampNonNegative(val(tds[6].querySelector("input")));

        const total = unit_price * qty;
        tds[7].textContent = fmt2(total);

        rows.push({
          brand,
          item_code,
          item_name,
          unit: "",
          tax_invoice_no,
          tax_invoice_date,
          unit_price,
          qty,
          note: "",
        });
      });
      return rows;
    },
  };

  const Subs = {
    tbody() {
      return byId("subs_table")?.querySelector("tbody");
    },

    addRow(data = {}) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.appendChild(makeInput("ชื่อผู้รับเหมาช่วง", data.vendor_name));

      const tdDate = document.createElement("td");
      tdDate.appendChild(makeInput("", data.pay_date, "input input-table mono", "date"));

      const tdAmt = document.createElement("td");
      tdAmt.className = "right";
      tdAmt.appendChild(makeInput("0.00", data.contract_amount, "input input-table right mono", "number"));

      const tdRate = document.createElement("td");
      tdRate.className = "right";
      tdRate.appendChild(makeInput("0", data.withholding_rate, "input input-table right mono", "number"));

      const tdWht = document.createElement("td");
      tdWht.className = "right";
      tdWht.appendChild(makeInput("0.00", data.withholding_amount, "input input-table right mono", "number"));

      const tdPay = document.createElement("td");
      tdPay.className = "right mono";
      tdPay.textContent = "0.00";

      const tdDel = document.createElement("td");
      tdDel.className = "right";
      const del = makeButton("ลบ", "btn btn-small btn-ghost");
      del.addEventListener("click", () => rowRemove(del));
      tdDel.appendChild(del);

      const rateInput = tdRate.querySelector("input");
      const amtInput = tdAmt.querySelector("input");
      const whtInput = tdWht.querySelector("input");

      function autoWht() {
        const amt = clampNonNegative(val(amtInput));
        let rate = clampNonNegative(val(rateInput));
        const current = clampNonNegative(val(whtInput));

        if (rate > 100) {
          rate = 100;
          rateInput.value = "100";
        }

        if (rate > 0 && current === 0 && amt > 0) {
          whtInput.value = (amt * rate / 100).toFixed(2);
        }
      }

      rateInput.addEventListener("blur", autoWht);
      amtInput.addEventListener("blur", autoWht);

      tr.append(tdName, tdDate, tdAmt, tdRate, tdWht, tdPay, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },

    read() {
      const rows = [];
      this.tbody()?.querySelectorAll("tr").forEach((tr) => {
        const tds = tr.querySelectorAll("td");

        const vendor_name = val(tds[0].querySelector("input")).trim();
        const pay_date = val(tds[1].querySelector("input")).trim();
        const contract_amount = clampNonNegative(val(tds[2].querySelector("input")));
        let withholding_rate = clampNonNegative(val(tds[3].querySelector("input")));
        let withholding_amount = clampNonNegative(val(tds[4].querySelector("input")));

        if (withholding_rate > 100) {
          withholding_rate = 100;
          tds[3].querySelector("input").value = "100";
        }

        if (withholding_amount > contract_amount) {
          withholding_amount = contract_amount;
          tds[4].querySelector("input").value = String(contract_amount);
        }

        const payable = Math.max(0, contract_amount - withholding_amount);
        tds[5].textContent = fmt2(payable);

        rows.push({
          vendor_name,
          pay_date,
          contract_amount,
          withholding_rate,
          withholding_amount,
          note: "",
        });
      });
      return rows;
    },
  };

  const Expenses = {
    tbody() {
      return byId("expenses_table")?.querySelector("tbody");
    },

    addRow(data = {}) {
      const tr = document.createElement("tr");

      const tdCat = document.createElement("td");
      tdCat.appendChild(makeInput("เช่น น้ำมัน", data.category || "อื่นๆ"));

      const tdTitle = document.createElement("td");
      tdTitle.appendChild(makeInput("รายการ", data.title));

      const tdDate = document.createElement("td");
      tdDate.appendChild(makeInput("", data.expense_date, "input input-table mono", "date"));

      const tdAmt = document.createElement("td");
      tdAmt.className = "right";
      tdAmt.appendChild(makeInput("0.00", data.amount, "input input-table right mono", "number"));

      const tdDel = document.createElement("td");
      tdDel.className = "right";
      const del = makeButton("ลบ", "btn btn-small btn-ghost");
      del.addEventListener("click", () => rowRemove(del));
      tdDel.appendChild(del);

      tr.append(tdCat, tdTitle, tdDate, tdAmt, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },

    read() {
      const rows = [];
      this.tbody()?.querySelectorAll("tr").forEach((tr) => {
        const tds = tr.querySelectorAll("td");
        const category = val(tds[0].querySelector("input")).trim() || "อื่นๆ";
        const title = val(tds[1].querySelector("input")).trim();
        const expense_date = val(tds[2].querySelector("input")).trim();
        const amount = clampNonNegative(val(tds[3].querySelector("input")));

        rows.push({
          category,
          title,
          expense_date,
          amount,
          note: "",
        });
      });
      return rows;
    },
  };

  const Advances = {
    tbody() {
      return byId("advances_table")?.querySelector("tbody");
    },

    addRow(data = {}) {
      const tr = document.createElement("tr");

      const tdTitle = document.createElement("td");
      tdTitle.appendChild(makeInput("รายการ", data.title));

      const tdDate = document.createElement("td");
      tdDate.appendChild(makeInput("", data.advance_date, "input input-table mono", "date"));

      const tdAmt = document.createElement("td");
      tdAmt.className = "right";
      tdAmt.appendChild(makeInput("0.00", data.amount, "input input-table right mono", "number"));

      const tdDel = document.createElement("td");
      tdDel.className = "right";
      const del = makeButton("ลบ", "btn btn-small btn-ghost");
      del.addEventListener("click", () => rowRemove(del));
      tdDel.appendChild(del);

      tr.append(tdTitle, tdDate, tdAmt, tdDel);
      this.tbody()?.appendChild(tr);
      ProjectForm.recalc();
    },

    read() {
      const rows = [];
      this.tbody()?.querySelectorAll("tr").forEach((tr) => {
        const tds = tr.querySelectorAll("td");
        const title = val(tds[0].querySelector("input")).trim();
        const advance_date = val(tds[1].querySelector("input")).trim();
        const amount = clampNonNegative(val(tds[2].querySelector("input")));

        rows.push({
          title,
          advance_date,
          amount,
          note: "",
        });
      });
      return rows;
    },
  };

  const ProjectForm = {
    recalc() {
      const mats = Materials.read();
      const subs = Subs.read();
      const exps = Expenses.read();
      const advs = Advances.read();

      const mt = mats.reduce((a, r) => a + (clampNonNegative(r.unit_price) * clampNonNegative(r.qty)), 0);
      const st = subs.reduce(
        (a, r) => a + Math.max(0, clampNonNegative(r.contract_amount) - clampNonNegative(r.withholding_amount)),
        0
      );
      const et = exps.reduce((a, r) => a + clampNonNegative(r.amount), 0);
      const at = advs.reduce((a, r) => a + clampNonNegative(r.amount), 0);

      byId("materials_total").textContent = fmt2(mt);
      byId("subs_total").textContent = fmt2(st);
      byId("expenses_total").textContent = fmt2(et);
      byId("advances_total").textContent = fmt2(at);
      byId("grand_total").textContent = fmt2(mt + st + et + at);
    },

    collect() {
      let status = val(byId("status")).trim();
      if (!allowedStatus.has(status)) {
        status = "IN_PROGRESS";
      }

      return {
        code: val(byId("code")).trim(),
        name: val(byId("name")).trim(),
        description: val(byId("description")).trim(),
        customer_name: val(byId("customer_name")).trim(),
        location: val(byId("location")).trim(),
        start_date: readDateValue("start_date"),
        end_date: readDateValue("end_date"),
        work_days: Math.max(0, Math.trunc(clampNonNegative(val(byId("work_days"))))),
        status,
        materials: Materials.read(),
        subcontractors: Subs.read(),
        expenses: Expenses.read(),
        advances: Advances.read(),
      };
    },

    validate(payload) {
      if (!payload.code) {
        return { ok: false, message: "กรุณาใส่รหัสโครงการ", focusId: "code" };
      }

      if (!payload.name) {
        return { ok: false, message: "กรุณาใส่ชื่อโครงการ", focusId: "name" };
      }

      if (!allowedStatus.has(payload.status)) {
        return { ok: false, message: "สถานะโครงการไม่ถูกต้อง", focusId: "status" };
      }

      const start = parseDateStr(payload.start_date);
      const end = parseDateStr(payload.end_date);
      if (start && end && end < start) {
        return {
          ok: false,
          message: "วันที่สิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น",
          focusId: "end_date",
        };
      }

      return { ok: true };
    },

    async save() {
      const hint = byId("save_hint");
      hint.textContent = "กำลังบันทึก...";

      const payload = this.collect();
      const check = this.validate(payload);

      if (!check.ok) {
        hint.textContent = check.message;
        const focusEl = byId(check.focusId);
        if (focusEl) focusEl.focus();
        return;
      }

      const id = window.__PROJECT__ && window.__PROJECT__.id;
      const url = id ? `/api/projects/${id}` : "/api/projects";
      const method = id ? "PUT" : "POST";

      try {
        const resp = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await resp.json().catch(() => ({ ok: false, error: "บันทึกไม่สำเร็จ" }));

        if (!resp.ok || !data.ok) {
          hint.textContent = data.error || "บันทึกไม่สำเร็จ";
          return;
        }

        hint.textContent = "บันทึกเรียบร้อย";
        const pid = data.id;
        setTimeout(() => {
          window.location.href = `/projects/${pid}`;
        }, 450);
      } catch (err) {
        hint.textContent = "เชื่อมต่อระบบไม่สำเร็จ";
      }
    },

    async remove(pid) {
      if (!confirm("ต้องการลบโครงการนี้ใช่หรือไม่?")) return;

      const hint = byId("save_hint");
      hint.textContent = "กำลังลบ...";

      try {
        const resp = await fetch(`/api/projects/${pid}`, { method: "DELETE" });
        const data = await resp.json().catch(() => ({ ok: false }));

        if (!resp.ok || !data.ok) {
          hint.textContent = "ลบไม่สำเร็จ";
          return;
        }

        window.location.href = "/projects";
      } catch (err) {
        hint.textContent = "เชื่อมต่อระบบไม่สำเร็จ";
      }
    },
  };

  window.Materials = Materials;
  window.Subs = Subs;
  window.Expenses = Expenses;
  window.Advances = Advances;
  window.ProjectForm = ProjectForm;

  const p = window.__PROJECT__ || {};

  (p.materials || []).forEach((r) => Materials.addRow(r));
  (p.subcontractors || []).forEach((r) => Subs.addRow(r));
  (p.expenses || []).forEach((r) => Expenses.addRow(r));
  (p.advances || []).forEach((r) => Advances.addRow(r));

  if ((p.materials || []).length === 0) Materials.addRow({});
  if ((p.subcontractors || []).length === 0) Subs.addRow({});
  if ((p.expenses || []).length === 0) Expenses.addRow({ category: "อื่นๆ" });
  if ((p.advances || []).length === 0) Advances.addRow({});

  ProjectForm.recalc();
})();