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
  // Match the original Nexora/S4P PAYMENT VOUCHER presentation, not the old
  // one-page mock slip. This preview remains DEMO-ONLY and never forges a
  // verification QR, payment evidence, journal or fiscal authorisation.
  function pdfText(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[\r\n\t]+/g, ' ')
      .replace(/[\u2013\u2014]/g, '-')
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201c\u201d]/g, '"')
      .replace(/[\u20ac]/g, 'EUR')
      .replace(/[^\x20-\xff]/g, '?')
      .replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  }
  function pdfDocument(record) {
    // Original Nexora report: letter page, branded header + document metadata,
    // beneficiary/payer, payment rows, strong total, evidence, signatures,
    // audit footer, and a second accounting/evidence annex.
    const pageWidth = 612;
    const pageHeight = 792;
    const navy = '0.043 0.153 0.290';
    const blue = '0.090 0.412 0.824';
    const muted = '0.310 0.380 0.463';
    const lineColor = '0.863 0.898 0.937';
    const ink = '0.106 0.153 0.200';
    const faint = '0.949 0.965 0.984';
    const gold = '0.714 0.490 0.192';
    const isOutflow = record.type === 'gasto';
    const typeTitle = isOutflow ? 'COMPROBANTE DE PAGO' : 'RECIBO DE INGRESO';
    const totalLabel = isOutflow ? 'TOTAL PAGADO' : 'TOTAL RECIBIDO';
    const paidToLabel = isOutflow ? 'PAGADO A / BENEFICIARIO' : 'RECIBIDO DE / REMITENTE';
    const paidByLabel = isOutflow ? 'PAGADO POR' : 'RECIBIDO POR';
    const subject = isOutflow ? 'Información del pago' : 'Información del ingreso';
    const currencyText = money(record.amount, record.currency);
    const dateParts = String(record.date).split('-');
    const displayDate = dateParts.length === 3 ? dateParts[2] + '/' + dateParts[1] + '/' + dateParts[0] : record.date;
    const docNumber = 'S4P-' + record.id;
    const pages = [];

    function draw() {
      const commands = [];
      const add = (value) => commands.push(value);
      function textAt(value, x, y, size, options) {
        const opts = options || {};
        const c = opts.color || ink;
        const font = opts.bold ? 'F2' : 'F1';
        add(c + ' rg\nBT /' + font + ' ' + size + ' Tf 1 0 0 1 ' + x + ' ' + y
          + ' Tm (' + pdfText(value) + ') Tj ET\n');
      }
      function fillRect(x, y, w, height, color) {
        add(color + ' rg\n' + x + ' ' + y + ' ' + w + ' ' + height + ' re f\n');
      }
      function strokeRect(x, y, w, height, color, weight) {
        add((color || lineColor) + ' RG\n' + (weight || 0.8) + ' w\n'
          + x + ' ' + y + ' ' + w + ' ' + height + ' re S\n');
      }
      function rule(x1, y1, x2, y2, color, weight) {
        add((color || lineColor) + ' RG\n' + (weight || 0.8) + ' w\n'
          + x1 + ' ' + y1 + ' m ' + x2 + ' ' + y2 + ' l S\n');
      }
      function chunks(value, limit, maxLines) {
        const source = String(value || '—').replace(/\s+/g, ' ').trim();
        const words = source.split(' ');
        const lines = [];
        let active = '';
        for (let word of words) {
          while (word.length > limit) {
            if (active) { lines.push(active); active = ''; }
            lines.push(word.slice(0, limit));
            word = word.slice(limit);
          }
          if (!word) continue;
          if (active.length + word.length + (active ? 1 : 0) > limit) {
            lines.push(active);
            active = word;
          } else {
            active += (active ? ' ' : '') + word;
          }
        }
        if (active) lines.push(active);
        if (maxLines && lines.length > maxLines) {
          const clipped = lines.slice(0, maxLines);
          clipped[maxLines - 1] = clipped[maxLines - 1].slice(0, Math.max(0, limit - 3)) + '...';
          return clipped;
        }
        return lines.length ? lines : ['—'];
      }
      function wrapped(value, x, y, maxChars, size, opts, maxLines) {
        const items = chunks(value, maxChars, maxLines);
        items.forEach((part, i) => textAt(part, x, y - i * (size + 4), size, opts));
        return y - items.length * (size + 4);
      }
      function section(title, y) {
        textAt(title, 50, y, 11, { bold: true, color: navy });
        rule(50, y - 7, 560, y - 7, blue, 1.25);
      }
      function footer(number) {
        rule(50, 60, 562, 60, lineColor, 0.75);
        textAt('S4P  ·  Comprobante ' + record.id + '  ·  NO VERIFICABLE - DEMOSTRACIÓN', 50, 44, 7.4, { color: muted });
        textAt('Página ' + number, 514, 44, 7.4, { color: muted });
      }
      return { add, textAt, fillRect, strokeRect, rule, section, wrapped, footer,
        output: () => commands.join('') };
    }

    // Page one - restore Nexora's corporate voucher arrangement.
    const one = draw();
    one.textAt('S4P', 50, 741, 22, { bold: true, color: navy });
    one.textAt('PLATAFORMA EMPRESARIAL', 50, 721, 9.2, { bold: true, color: blue });
    one.textAt('Empresa de demostración', 50, 702, 10, { bold: true });
    one.textAt('Honduras  ·  Identidad y cifras ficticias', 50, 686, 8, { color: muted });
    one.fillRect(348, 644, 211, 112, faint);
    one.strokeRect(348, 644, 211, 112, lineColor);
    one.textAt(typeTitle, 358, 735, 9, { bold: true, color: blue });
    one.textAt('N.º ' + docNumber, 358, 716, 13, { bold: true, color: navy });
    one.textAt('Emitido ' + displayDate, 358, 696, 8.3, { color: muted });
    one.textAt('Contabilizado: no aplica', 358, 680, 8.3, { color: muted });
    one.textAt('Estado: DEMOSTRACIÓN', 358, 664, 8.3, { bold: true, color: gold });

    one.strokeRect(479, 562, 78, 69, lineColor, 0.8);
    one.textAt('QR', 505, 599, 13, { bold: true, color: muted });
    one.textAt('NO ACTIVO', 487, 579, 8.3, { bold: true, color: gold });
    one.rule(50, 551, 559, 551, navy, 1.8);
    one.textAt('La verificación por QR corresponde solo a comprobantes oficiales emitidos por el ERP.', 50, 536, 8, { color: muted });

    one.textAt(paidToLabel, 50, 503, 8, { bold: true, color: muted });
    one.wrapped(record.party, 50, 487, 40, 10.5, { bold: true, color: ink }, 2);
    one.textAt(paidByLabel, 326, 503, 8, { bold: true, color: muted });
    one.wrapped('Empresa S4P (demostración)', 326, 487, 31, 9.8, { bold: true, color: ink }, 2);
    one.section(subject, 452);

    const info = [
      ['Concepto', record.description],
      ['Ámbito', 'Operación general · DEMO'],
      ['Método', isOutflow ? 'Efectivo (simulado)' : 'Ingreso simulado'],
    ];
    if (record.type === 'remesa') {
      info.push(['Remesadora', record.provider || 'Sin especificar']);
    }
    if (record.category) {
      info.push(['Categoría', record.category]);
    }
    if (record.reference) {
      info.push(['Referencia', record.reference]);
    }
    let y = 425;
    for (const [label, value] of info) {
      one.textAt(label, 52, y, 8.3, { bold: true, color: muted });
      y = one.wrapped(value, 171, y, 62, 9.6, { color: ink }, 2) - 10;
    }
    const totalY = Math.max(224, Math.min(270, y - 12));
    one.rule(50, totalY + 36, 560, totalY + 36, navy, 1.5);
    one.rule(50, totalY - 11, 560, totalY - 11, navy, 1.5);
    one.textAt(totalLabel, 52, totalY + 6, 9.2, { bold: true, color: muted });
    one.textAt(currencyText, 359, totalY, 19, { bold: true, color: navy });
    const evidenceY = totalY - 48;
    one.section('Evidencia de pago', evidenceY);
    one.textAt('Sin evidencia adjunta: documento generado en una vista de prueba.', 52, evidenceY - 23, 8.7, { color: muted });
    const signatureY = Math.min(126, evidenceY - 80);
    const positions = [50, 221, 392];
    const signatures = [
      ['Preparado por', 'S4P · DEMO'],
      ['Aprobado por', 'Pendiente de aprobación'],
      ['Recibí conforme', record.party],
    ];
    signatures.forEach(([label, name], index) => {
      const x = positions[index];
      one.rule(x, signatureY + 9, x + 151, signatureY + 9, muted, 0.75);
      one.textAt(label, x, signatureY - 6, 8, { bold: true, color: muted });
      one.wrapped(name, x, signatureY - 21, 23, 8.5, { color: ink }, 2);
    });
    one.textAt('SIN VALIDEZ CONTABLE, FISCAL NI BANCARIA · NO HAY FIRMA NI APROBACIÓN REAL',
      50, 76, 8.5, { bold: true, color: gold });
    one.footer(1);
    pages.push(one.output());

    // Page two - same accounting/evidence appendix as the Nexora template.
    // Example entries are illustrative only, never actual journal postings.
    const two = draw();
    two.textAt('S4P', 50, 746, 21, { bold: true, color: navy });
    two.textAt('ANEXO AL ' + typeTitle, 50, 725, 11.5, { bold: true, color: blue });
    two.textAt('Documento ' + docNumber + ' · ' + displayDate, 50, 703, 9.5, { color: muted });
    two.rule(50, 688, 560, 688, navy, 1.6);
    two.section('Asiento contable (ilustrativo - NO contabilizado)', 661);
    two.fillRect(50, 598, 510, 35, faint);
    two.textAt('Código / Cuenta', 58, 612, 9, { bold: true, color: muted });
    two.textAt('Débito', 360, 612, 9, { bold: true, color: muted });
    two.textAt('Crédito', 469, 612, 9, { bold: true, color: muted });
    const debitAccount = isOutflow ? '5100 - Gastos generales (ejemplo)' : '1101 - Caja / Banco (ejemplo)';
    const creditAccount = isOutflow ? '1101 - Caja / Banco (ejemplo)' : '3100 - Origen de fondos (ejemplo)';
    two.textAt(debitAccount, 58, 577, 9.2);
    two.textAt(currencyText, 360, 577, 9.2);
    two.rule(50, 565, 560, 565, lineColor, 0.5);
    two.textAt(creditAccount, 58, 547, 9.2);
    two.textAt(currencyText, 469, 547, 9.2);
    two.rule(50, 532, 560, 532, lineColor, 0.65);
    two.textAt('Totales', 58, 509, 9.5, { bold: true, color: navy });
    two.textAt(currencyText, 360, 509, 9.5, { bold: true, color: navy });
    two.textAt(currencyText, 469, 509, 9.5, { bold: true, color: navy });
    two.rule(50, 495, 560, 495, navy, 0.8);
    two.wrapped('Doble partida ilustrativa. No existe documento contable registrado,',
      50, 475, 86, 8.5, { color: muted }, 2);
    two.textAt('sello de aprobación, movimiento bancario ni afectación a la tesorería real.',
      50, 463, 8.5, { color: muted });
    two.section('Evidencia de pago', 421);
    two.textAt('No existe archivo de evidencia real porque esta operación es una demostración.', 52, 397, 9, { color: muted });
    two.section('Datos del documento', 349);
    const appendix = [
      ['Comprobante', docNumber],
      ['Beneficiario', record.party],
      ['Monto', currencyText],
      ['Fecha', displayDate],
      ['Referencia', record.reference || 'Sin referencia'],
      ['Verificación', 'No disponible en la demostración'],
    ];
    let rowY = 320;
    for (const [name, value] of appendix) {
      two.textAt(name, 52, rowY, 8.5, { bold: true, color: muted });
      two.wrapped(value, 175, rowY, 58, 9, {}, 1);
      rowY -= 24;
    }
    two.fillRect(50, 105, 510, 48, faint);
    two.textAt('SOLO VALIDACIÓN VISUAL DEL FORMATO NEXORA / S4P', 60, 133, 10, { bold: true, color: gold });
    two.textAt('SIN VALIDEZ CONTABLE, FISCAL NI BANCARIA. No usar como recibo real.',
      60, 113, 8.5, { color: muted });
    two.footer(2);
    pages.push(two.output());

    // PDF 1.4 with searchable, selectable text and two US-letter pages.
    // All stored characters use the WinAnsi-compatible 1-byte range, so
    // object offsets and /Length are byte-accurate even for Spanish accents.
    let out = '%PDF-1.4\n%S4P-NEXORA-TEMPLATE-DEMO\n';
    const positionsOut = [0];
    function addObject(number, content) {
      positionsOut[number] = out.length;
      out += number + ' 0 obj\n' + content + '\nendobj\n';
    }
    addObject(1, '<< /Type /Catalog /Pages 2 0 R >>');
    addObject(2, '<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>');
    const fontResources = '/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >>';
    addObject(3, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + pageWidth + ' ' + pageHeight
      + '] ' + fontResources + ' /Contents 7 0 R >>');
    addObject(4, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
    addObject(5, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
    addObject(6, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + pageWidth + ' ' + pageHeight
      + '] ' + fontResources + ' /Contents 8 0 R >>');
    addObject(7, '<< /Length ' + pages[0].length + ' >>\nstream\n' + pages[0] + 'endstream');
    addObject(8, '<< /Length ' + pages[1].length + ' >>\nstream\n' + pages[1] + 'endstream');
    const xrefOffset = out.length;
    out += 'xref\n0 9\n0000000000 65535 f \n';
    for (let number = 1; number <= 8; number++) {
      out += String(positionsOut[number]).padStart(10, '0') + ' 00000 n \n';
    }
    out += 'trailer\n<< /Size 9 /Root 1 0 R >>\nstartxref\n'
      + xrefOffset + '\n%%EOF\n';
    return new Blob(
      [Uint8Array.from(out, (character) => character.charCodeAt(0) & 255)],
      { type: 'application/pdf' },
    );
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
