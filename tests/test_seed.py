from app.db import connect, init_db
from scripts.seed import seed


def test_seed_is_repeatable(schema):
    try:
        snapshots = []
        for run in range(2):
            seed('small', schema)
            snapshot = {}
            with connect(schema) as db:
                for table in ('users', 'categories', 'tickets', 'comments'):
                    snapshot[table] = db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                ticket = db.execute("INSERT INTO tickets (user_id, category_id, title, body) VALUES (2, 1, 'Новая', 'Текст') RETURNING id").fetchone()
                assert ticket['id'] == 301
            snapshots.append(snapshot)
        assert snapshots[0] == snapshots[1]
        for table, count in [('users', 50), ('categories', 5), ('tickets', 300), ('comments', 900)]:
            assert len(snapshots[0][table]) == count
    finally:
        init_db(schema, reset=True)
