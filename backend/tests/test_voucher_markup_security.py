"""Untrusted voucher text must never load a resource through ReportLab markup."""
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.helpers import create_company, login_admin
from tests.test_company_branding_voucher import _outflow


@pytest.mark.parametrize('field', ['beneficiary', 'companyName', 'companyFooter'])
def test_voucher_text_markup_cannot_fetch_loopback_image(client, field, tmp_path):
    requests = []

    class Probe(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Probe)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        login_admin(client)
        company = create_company(client, name='S4P markup security QA')
        document_id = uuid.UUID(_outflow(client, company['id']))
        result = client.patch(f"/api/master-data/companies/{company['id']}",
                              json={'voucherApproverName': 'QA Approver'})
        assert result.status_code == 200
        payload = f'QA <img src="http://127.0.0.1:{server.server_port}/probe.png" width="1" height="1"/>'
        if field != 'beneficiary':
            update = {'name': payload} if field == 'companyName' else {'voucherFooterText': payload}
            result = client.patch(f"/api/master-data/companies/{company['id']}/profile", json=update)
            assert result.status_code == 200, result.text
        response = client.get(f'/api/treasury/vouchers/{document_id}',
                              params={'beneficiary': payload if field == 'beneficiary' else 'QA Supplier',
                                      'paymentMethod': 'Efectivo'})
        assert requests == [], 'Untrusted text caused an SSRF request'
        assert response.status_code == 200, response.text
        (tmp_path / f'{field}.pdf').write_bytes(response.content)
        assert b'127.0.0.1' in response.content
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
