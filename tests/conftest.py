from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.db import connect, get_db, init_db
from app.main import app
from app.rules import hash_password


@pytest.fixture(scope='session')
def schema():
    name = 'test_' + uuid4().hex
    init_db(name)
    yield name
    with connect() as db:
        db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))


@pytest.fixture
def db(schema):
    conn = connect(schema)
    password = hash_password('demo')
    conn.execute('INSERT INTO users (id, username, password_hash, is_staff) VALUES (1, %s, %s, true), (2, %s, %s, false), (3, %s, %s, false)',
                 ('staff', password, 'demo', password, 'other', password))
    conn.execute("INSERT INTO categories (id, name, response_minutes) VALUES (1, 'Почта', 60), (2, 'Сеть', 30)")
    conn.execute("INSERT INTO tickets (id, user_id, category_id, title, body, created_at) VALUES (1, 2, 1, 'Ошибка', 'Не работает почта', %s)",
                 (datetime(2026, 1, 1, tzinfo=timezone.utc),))
    conn.execute("SELECT setval(pg_get_serial_sequence('tickets', 'id'), 1)")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def client(db):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        client.post('/login', data={'username': 'demo', 'password': 'demo'})
        yield client
    app.dependency_overrides.clear()
