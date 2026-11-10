"""Real PostgreSQL checkout contention must not block ASGI response cleanup."""
import asyncio
import threading
import time

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.api import edit_access_guard
from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.models.user import User
from app.services.permission_service import require_permission
from tests.helpers import login_admin
from tests.test_edit_access import _configure_test_pin


@pytest.mark.parametrize('boundary', ['protected-edit', 'rbac'])
def test_pool_wait_keeps_event_loop_available_to_release_connections(client, db_session, monkeypatch, boundary):
    login_admin(client)
    user = db_session.scalar(select(User).where(User.email == 'admin@nexora.group'))
    db_session.expunge(user)
    db_session.rollback()
    settings = get_settings().model_copy()
    settings.edit_access_required = True
    _configure_test_pin(settings, 'local-contention-test-only')
    engine = create_engine(settings.database_url, pool_size=1, max_overflow=0, pool_timeout=1.5)
    sessions = sessionmaker(bind=engine)
    release = threading.Event()
    held = threading.Event()

    def hold_connection():
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            held.set()
            assert release.wait(5), 'test must release its own held connection'

    app = FastAPI()

    @app.get('/release')
    async def release_from_event_loop():
        release.set()
        return {'released': True}

    if boundary == 'protected-edit':
        monkeypatch.setattr(edit_access_guard, 'SessionLocal', sessions)
        monkeypatch.setattr(edit_access_guard, 'get_settings', lambda: settings)
        edit_access_guard.register_edit_access_guard(app)

        @app.put('/api/protected')
        def protected():
            return {'unexpected': 'capability is deliberately absent'}

        method, path, expected = 'PUT', '/api/protected', 428
    else:
        def real_database():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = real_database
        # Identity from the real fixture login. The permission query is real SQL.
        app.dependency_overrides[get_current_user] = lambda: (user, ['Administrator'])

        @app.get('/rbac')
        def guarded(actor=Depends(require_permission('core.company', 'read'))):
            return {'id': str(actor.id)}

        method, path, expected = 'GET', '/rbac', 200

    holder = threading.Thread(target=hold_connection)
    holder.start()
    assert held.wait(3)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://qa.local',
                                   cookies={settings.session_cookie_name: client.cookies.get(settings.session_cookie_name)}) as api:
            started = time.monotonic()
            waiting = asyncio.create_task(api.request(method, path))
            try:
                await asyncio.sleep(0.05)
                heartbeat = await api.get('/release')
                assert heartbeat.status_code == 200
                assert time.monotonic() - started < 1.0, 'SQL checkout blocked the event loop until pool timeout'
                response = await asyncio.wait_for(waiting, timeout=3)
                assert response.status_code == expected, response.text
            finally:
                release.set()
                await asyncio.gather(waiting, return_exceptions=True)

    try:
        asyncio.run(exercise())
        holder.join(timeout=3)
        assert not holder.is_alive()
        assert engine.pool.checkedout() == 0
    finally:
        release.set()
        holder.join(timeout=3)
        engine.dispose()


def test_authenticated_burst_shares_db_budget_and_creates_preferences_atomically(client, db_session, monkeypatch):
    from anyio import CapacityLimiter
    from sqlalchemy import func

    from app.api import deps
    from app.api.routes import edit_access as edit_routes
    from app.main import create_app
    from app.models.edit_access import EditAccessEvent
    from app.models.user_preference import UserPreference

    login_admin(client)
    settings = get_settings().model_copy()
    settings.edit_access_required = True
    settings.edit_access_max_uses = 128
    _configure_test_pin(settings, 'local-admission-test-only')
    engine = create_engine(settings.database_url, pool_size=2, max_overflow=0, pool_timeout=1.5)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(deps, 'SessionLocal', sessions)
    monkeypatch.setattr(edit_access_guard, 'SessionLocal', sessions)
    monkeypatch.setattr(edit_access_guard, 'get_settings', lambda: settings)
    monkeypatch.setattr(edit_routes, 'get_settings', lambda: settings)
    app = create_app()
    app.state.database_capacity = CapacityLimiter(2)
    cookie = {settings.session_cookie_name: client.cookies.get(settings.session_cookie_name)}

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver',
                                   cookies=cookie, headers={'Origin': settings.frontend_url}) as api:
            verified = await api.post('/api/edit-access/verify', json={'token': 'local-admission-test-only'})
            assert verified.status_code == 200, verified.text
            capability = verified.json()['capability']

            async def request(index):
                if index % 2 == 0:
                    return await api.get('/api/master-data/companies')
                return await api.put('/api/me/preferences',
                    json={'themeId': 'sap-gui-horizon', 'density': 'compact'},
                    headers={'X-Nexora-Edit-Access': capability})

            responses = await asyncio.wait_for(asyncio.gather(*(request(i) for i in range(48))), timeout=10)
            assert [response.status_code for response in responses] == [200] * 48
            saved = await api.get('/api/me/preferences')
            assert saved.json() == {'themeId': 'sap-gui-horizon', 'density': 'compact'}

    try:
        asyncio.run(exercise())
        assert engine.pool.checkedout() == 0
        db_session.rollback()
        assert db_session.scalar(select(func.count()).select_from(UserPreference)) == 1
        assert db_session.scalar(select(func.count()).select_from(EditAccessEvent).where(
            EditAccessEvent.outcome == 'MUTATION_ALLOWED')) == 24
    finally:
        engine.dispose()
