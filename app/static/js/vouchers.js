(function () {
  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  // ✅ นับ/ส่งแบบ "unique ตาม value" เพื่อกัน checkbox ซ้ำ (desktop+mobile)
  function selectedIds() {
    const set = new Set();
    qsa('input.js-vchk:checked').forEach(el => {
      const v = (el.value || '').trim();
      if (v) set.add(v);
    });
    return Array.from(set);
  }

  // ✅ อัปเดตจำนวนที่เลือก (ถ้ามี element โชว์จำนวน เช่น #voucher_selected_count)
  function updateSelectedCount() {
    const el = qs('#voucher_selected_count');
    if (!el) return;
    el.textContent = String(selectedIds().length);
  }

  // ✅ เวลา user ติ๊กตัวใดตัวหนึ่ง ให้ sync checkbox ที่มี value เดียวกัน (อีก view ที่ซ่อนอยู่)
  function syncSameValue(changedEl) {
    const v = (changedEl.value || '').trim();
    if (!v) return;

    const checked = !!changedEl.checked;
    qsa('input.js-vchk').forEach(el => {
      if ((el.value || '').trim() === v) el.checked = checked;
    });
  }

  // ✅ hook events: change ของ checkbox + นับจำนวนตอนแรก
  function bind() {
    // จับทุก checkbox (ทั้ง desktop และ mobile)
    qsa('input.js-vchk').forEach(el => {
      el.addEventListener('change', function () {
        syncSameValue(this);
        updateSelectedCount();
      });
    });

    // ถ้ามีปุ่ม/โค้ดอื่นเปลี่ยน checked โดยไม่ยิง change:
    // เรียก updateSelectedCount() หลัง toggleAll ได้แล้ว
    updateSelectedCount();
  }

  window.Vouchers = {
    print: function () {
      const ids = selectedIds();
      const docType = (qs('#voucher_doc_type')?.value || 'PV');

      if (!ids.length) {
        alert('กรุณาเลือกรายการอย่างน้อย 1 รายการ');
        return;
      }

      const form = qs('#voucher_print_form');
      qs('#voucher_ids', form).value = ids.join(',');
      qs('#voucher_doc_type_hidden', form).value = docType;

      // เผื่อมี UI แสดงจำนวน
      updateSelectedCount();

      form.submit();
    },

    toggleAll: function (tableId, checked) {
      const table = qs(tableId);
      if (!table) return;

      // ตั้งค่าทุก checkbox ใน "container" ที่ส่งมา
      qsa('input.js-vchk', table).forEach(el => { el.checked = checked; });

      // ✅ sync ไปยัง checkbox ฝั่งที่ซ่อนอยู่ด้วย (value เดียวกัน)
      const set = new Set();
      qsa('input.js-vchk', table).forEach(el => {
        const v = (el.value || '').trim();
        if (v) set.add(v);
      });

      qsa('input.js-vchk').forEach(el => {
        const v = (el.value || '').trim();
        if (set.has(v)) el.checked = checked;
      });

      updateSelectedCount();
    },

    // เผื่อเรียกจากปุ่ม "ล้างที่เลือก"
    clearAll: function () {
      qsa('input.js-vchk').forEach(el => { el.checked = false; });
      updateSelectedCount();
    },

    // เผื่อเรียกจากปุ่ม "อัปเดตจำนวน" (ถ้าต้องการ)
    updateCount: function () {
      updateSelectedCount();
    }
  };

  // auto bind
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
