from app.db import connect, init_db


def test_reset_clears_data_and_restarts_ids(schema):
    with connect(schema) as db:
        db.execute("INSERT INTO users (username, password_hash) VALUES ('test', 'hash')")
    init_db(schema, reset=True)
    init_db(schema, reset=True)
    with connect(schema) as db:
        for table in ('users', 'categories', 'tickets', 'comments'):
            assert db.execute(f'SELECT count(*) AS count FROM {table}').fetchone()['count'] == 0
        user = db.execute("INSERT INTO users (username, password_hash) VALUES ('test', 'hash') RETURNING id").fetchone()
        assert user['id'] == 1
        db.rollback()
