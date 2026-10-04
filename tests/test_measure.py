from app.db import MeasuredDB
from scripts.measure import summarize


def test_sql_measurement(db):
    timing = {'db_ms': 0, 'queries': 0}
    measured = MeasuredDB(db, timing)
    assert measured.execute('SELECT 1 AS value').fetchone()['value'] == 1
    assert measured.execute('SELECT 2 AS value').fetchone()['value'] == 2
    assert timing['queries'] == 2
    assert timing['db_ms'] > 0


def test_statistics_exclude_warmup():
    rows = []
    for i in range(21):
        phase = 'measure'
        value = i
        if i == 0:
            phase = 'warmup'
            value = 999
        rows.append({'operation': 'test', 'phase': phase, 'http_ms': value,
                     'server_ms': 10, 'db_ms': 4, 'app_ms': 6, 'sql_count': 3})
    result = summarize(rows)[0]
    assert result['samples'] == 20
    assert result['p50_ms'] == 10.5
    assert result['p95_ms'] == 19
    assert result['max_ms'] == 20
    assert result['server_mean_ms'] == result['db_mean_ms'] + result['app_mean_ms']
    assert result['sql_count_mean'] == 3
