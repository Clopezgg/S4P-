/* Interactive financial workflow preview. DEMO ONLY: nothing is sent to the ERP. */
(function () {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const records = [];
  const labels = { remesa: 'Registrar remesa', gasto: 'Registrar gasto', recibo: 'Generar recibo PDF' };
  const names = { remesa: 'Remesa recibida', gasto: 'Gasto registrado', recibo: 'Recibo de ingreso' };
  let currentType = '';
  let seq = 0;
  let lastFocus = null;
  let toastTimeout;

  function esc(text) {
    return String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function money(amount, currency) {
    return (currency === 'USD' ? '$ ' : 'L ') + new Intl.NumberFormat('es-HN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
  }
  function field(name, label, extra, wide) {
    return '<div class="finance-demo-field' + (wide ? ' wide' : '') + '"><label for="fd-' + name + '">' + label + '</label><input id="fd-' + name + '" name="' + name + '" ' + extra + ' required></div>';
  }
  function fieldsFor(kind) {
    let specific = '';
    if (kind === 'remesa') {
      specific = field('party', 'Remitente / quien envía', 'maxlength="90" placeholder="Nombre del remitente"', true)
        + field('provider', 'Empresa remesadora', 'maxlength="80" placeholder="Entidad de envío"', true)
        + field('reference', 'Referencia de remesa', 'maxlength="48" placeholder="Número de referencia"', true);
    } else if (kind === 'gasto') {
      specific = field('party', 'Proveedor / beneficiario', 'maxlength="90" placeholder="Nombre del beneficiario"', true)
        + '<div class="finance-demo-field wide"><label for="fd-category">Categoría del gasto</label>'
        + '<select id="fd-category" name="category" required><option value="">Seleccione</option><option>Servicios</option><option>Transporte</option><option>Mantenimiento</option><option>Compra menor</option><option>Otros gastos</option></select></div>';
    } else {
      specific = field('party', 'Recibido de', 'maxlength="90" placeholder="Persona o entidad"', true)
        + field('reference', 'Referencia del cobro', 'maxlength="48" placeholder="Referencia opcional"', true);
    }
    return specific
      + field('amount', 'Monto', 'type="number" min="0.01" step="0.01" max="999999999.99" inputmode="decimal" placeholder="0.00"', false)
      + '<div class="finance-demo-field"><label for="fd-currency">Moneda</label><select id="fd-currency" name="currency" required><option value="HNL">HNL · Lempiras</option><option value="USD">USD · Dólares</option></select></div>'
      + field('date', 'Fecha de la operación', 'type="date"', true)
      + '<div class="finance-demo-field wide"><label for="fd-description">Concepto / descripción</label><textarea id="fd-description" name="description" maxlength="180" required placeholder="Explique el motivo de la operación"></textarea></div>';
  }
  function closeForm() {
    const modal = byId('finance-demo-modal');
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.isConnected) lastFocus.focus();
  }
  function openForm(type, trigger) {
    if (!labels[type]) return;
    ['drawer-scrim','sheet-scrim'].forEach((id) => { const el = byId(id); if (el) el.classList.remove('show'); });
    lastFocus = trigger || document.activeElement;
    currentType = type;
    byId('finance-demo-title').textContent = labels[type];
    byId('finance-demo-description').textContent = type === 'recibo'
      ? 'Cree un recibo de ejemplo y descargue su PDF. El archivo indicará que no tiene validez financiera.'
      : 'Complete los datos para simular el registro. No se crean asientos ni se modifica tesorería.';
    byId('finance-demo-submit').textContent = type === 'recibo' ? 'Generar PDF de ejemplo' : 'Registrar en demostración';
    byId('finance-demo-fields').innerHTML = fieldsFor(type);
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    byId('fd-date').value = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
    byId('finance-demo-modal').hidden = false;
    document.body.style.overflow = 'hidden';
    byId('fd-party').focus();
  }
  function toast(message) {
    const notice = byId('finance-demo-toast');
    notice.textContent = message;
    notice.hidden = false;
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => { notice.hidden = true; }, 6000);
  }
  function renderRecords() {
    const container = byId('finance-demo-records');
    const box = byId('finance-demo-results');
    container.replaceChildren();
    box.hidden = records.length === 0;
    for (const record of records) {
      const row = document.createElement('div');
      row.className = 'finance-demo-row';
      const info = document.createElement('div');
      info.className = 'finance-demo-row__text';
      const strong = document.createElement('strong');
      strong.textContent = names[record.type] + ' · ' + record.party;
      const small = document.createElement('small');
      small.textContent = record.id + ' · ' + record.date + ' · Solo demostración';
      info.append(strong, small);
      const actions = document.createElement('div');
      actions.className = 'finance-demo-row__actions';
      const amount = document.createElement('b');
      amount.textContent = money(record.amount, record.currency);
      const pdf = document.createElement('button');
      pdf.type = 'button';
      pdf.className = 'finance-demo-pdf';
      pdf.textContent = 'Descargar PDF';
      pdf.setAttribute('aria-label', 'Descargar PDF ' + record.id);
      pdf.addEventListener('click', () => downloadReceipt(record));
      actions.append(amount, pdf);
      row.append(info, actions);
      container.appendChild(row);
    }
  }
  function pdfText(text) {
    return String(text || '').normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^\x20-\x7e]/g, '?')
      .replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  }
  function pdfDocument(record) {
    // A self-contained 1-page PDF 1.4 generated locally; no CDN, API, cache or stored data.
    const textAt = (text, x, y, size) => 'BT /F1 ' + size + ' Tf ' + x + ' ' + y + ' Td (' + pdfText(text) + ') Tj ET\n';
    const separator = '0.75 0.82 0.88 RG 48 640 m 544 640 l S\n';
    let stream = '0.06 0.12 0.21 rg\n';
    stream += textAt('S4P | PLATAFORMA EMPRESARIAL', 48, 785, 19);
    stream += '0.65 0.36 0.10 rg\n' + textAt('RECIBO DE DEMOSTRACION', 48, 751, 16);
    stream += '0.35 0.40 0.48 rg\n' + textAt('SIN VALIDEZ CONTABLE, FISCAL NI BANCARIA', 48, 728, 10);
    stream += '0.08 0.19 0.30 rg\n';
    stream += textAt('Documento: ' + record.id, 48, 687, 12);
    stream += textAt('Fecha: ' + record.date, 48, 665, 12);
    stream += separator;
    stream += textAt('Tipo: ' + names[record.type], 48, 604, 12);
    stream += textAt((record.type === 'gasto' ? 'Beneficiario: ' : 'Recibido de: ') + record.party, 48, 578, 12);
    stream += textAt('Monto: ' + money(record.amount, record.currency), 48, 552, 14);
    stream += textAt('Moneda: ' + record.currency, 48, 525, 12);
    stream += textAt('Referencia: ' + (record.reference || 'No registrada'), 48, 499, 12);
    stream += textAt('Concepto:', 48, 469, 12);
    // Avoid cutting long user descriptions beyond the printed page.
    const summary = record.description.replace(/[\r\n]/g, ' ').slice(0, 160);
    stream += textAt(summary.slice(0, 77), 48, 444, 11);
    if (summary.length > 77) stream += textAt(summary.slice(77, 154), 48, 425, 11);
    stream += '0.65 0.36 0.10 rg\n' + textAt('DATOS FICTICIOS - DOCUMENTO SOLO PARA VALIDAR LA INTERFAZ', 48, 115, 10);
    stream += '0.4 0.46 0.55 rg\n' + textAt('No representa un pago, remesa, asiento contable ni recibo real.', 48, 94, 10);

    // PDF objects and xref use ASCII-only strings, therefore byte offsets == string lengths.
    let out = '%PDF-1.4\n%S4P-DEMO\n';
    const offsets = [0];
    const add = (id, body) => { offsets[id] = out.length; out += id + ' 0 obj\n' + body + '\nendobj\n'; };
    add(1, '<< /Type /Catalog /Pages 2 0 R >>');
    add(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
    add(3, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>');
    add(4, '<< /Length ' + stream.length + ' >>\nstream\n' + stream + 'endstream');
    add(5, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    const at = out.length;
    out += 'xref\n0 6\n0000000000 65535 f \n';
    for (let id = 1; id < 6; id++) out += String(offsets[id]).padStart(10, '0') + ' 00000 n \n';
    out += 'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + at + '\n%%EOF\n';
    return new Blob([out], { type: 'application/pdf' });
  }
  function downloadReceipt(record) {
    const file = pdfDocument(record);
    const href = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = href;
    link.download = 'S4P-RECIBO-DEMO-' + record.id + '.pdf';
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    // iOS Safari can cancel a download if its blob URL is immediately revoked.
    setTimeout(() => { link.remove(); URL.revokeObjectURL(href); }, 30_000);
    toast('PDF de ejemplo generado: ' + record.id + '. No tiene validez financiera.');
  }

  document.addEventListener('click', (event) => {
    const flow = event.target.closest('[data-flow]');
    if (flow) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openForm(flow.getAttribute('data-flow'), flow);
      return;
    }
    const oldQuick = event.target.closest('[data-quick]');
    if (oldQuick) {
      const label = oldQuick.getAttribute('data-quick') || '';
      const type = /remesa/i.test(label) ? 'remesa' : /gasto/i.test(label) ? 'gasto' :
        /recibo|comprobante/i.test(label) ? 'recibo' : '';
      if (type) {
        event.preventDefault();
        event.stopImmediatePropagation();
        openForm(type, oldQuick);
      }
    }
  }, true);

  document.querySelectorAll('[data-finance-close]').forEach((button) => button.addEventListener('click', closeForm));
  byId('finance-demo-modal').addEventListener('click', (event) => {
    if (event.target === byId('finance-demo-modal')) closeForm();
  });
  document.addEventListener('keydown', (event) => {
    if (byId('finance-demo-modal').hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeForm();
    }
  });
  byId('finance-demo-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const fields = Object.fromEntries(new FormData(form).entries());
    const amount = Number(fields.amount);
    if (!Number.isFinite(amount) || amount < 0.01 || amount > 999999999.99) {
      byId('fd-amount').setCustomValidity('Ingrese un monto válido superior a cero.');
      byId('fd-amount').reportValidity();
      byId('fd-amount').setCustomValidity('');
      return;
    }
    const kind = currentType;
    if (!labels[kind]) return;
    const record = {
      id: 'DEMO-' + String(++seq).padStart(4, '0'),
      type: kind,
      party: String(fields.party || '').trim().slice(0, 90),
      provider: String(fields.provider || '').trim().slice(0, 80),
      reference: String(fields.reference || '').trim().slice(0, 48),
      category: String(fields.category || '').trim(),
      amount: Math.round(amount * 100) / 100,
      currency: fields.currency === 'USD' ? 'USD' : 'HNL',
      date: String(fields.date || ''),
      description: String(fields.description || '').trim().slice(0, 180),
    };
    if (!record.party || !record.description || !record.date) return;
    records.unshift(record);
    renderRecords();
    closeForm();
    // The receipt is downloadable for any demo operation; nothing is posted to an API.
    if (kind === 'recibo') downloadReceipt(record);
    else toast((kind === 'remesa' ? 'Remesa' : 'Gasto') + ' registrado SOLO en la demostración. ' + record.id + '. Puede generar su PDF desde Finanzas.');
  });
})();
