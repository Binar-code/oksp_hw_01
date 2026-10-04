import argparse
import csv
import math
import statistics
import time
from pathlib import Path

import httpx

from app.db import connect

TABLES = ['users', 'categories', 'tickets', 'comments']


OPERATIONS = [
    ('GET /', 'GET', '/', 200),
    ('GET /tickets/1', 'GET', '/tickets/1', 200),
    ('GET /summary', 'GET', '/summary', 200),
    ('GET /login', 'GET', '/login', 200),
    ('POST /login', 'POST', '/login', 303),
    ('POST /logout', 'POST', '/logout', 303),
    ('POST /api/tickets', 'POST', '/api/tickets', 201),
    ('POST /api/tickets/{id}/comments', 'POST', '', 201),
    ('PATCH status -> in_progress', 'PATCH', '', 200),
]


def counts():
    result = {}
    with connect() as db:
        for table in TABLES:
            result[table] = db.execute(f'SELECT count(*) AS count FROM {table}').fetchone()['count']
    return result


def save_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def print_table(headers, rows):
    widths = []
    for header in headers:
        widths.append(len(header))
    for row in rows:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(str(value)))
    border = '+'
    for width in widths:
        border += '-' * (width + 2) + '+'
    print(border)
    for row in [headers] + rows:
        line = '|'
        for i, value in enumerate(row):
            text = str(value)
            if i == 0:
                text = text.ljust(widths[i])
            else:
                text = text.rjust(widths[i])
            line += ' ' + text + ' |'
        print(line)
        if row is headers:
            print(border)
    print(border)


def summarize(rows):
    groups = {}
    for row in rows:
        if row['phase'] == 'measure':
            name = row['operation']
            if name not in groups:
                groups[name] = []
            groups[name].append(row)
    result = []
    for name, samples in groups.items():
        http, server, database, application, queries = [], [], [], [], []
        for sample in samples:
            http.append(sample['http_ms'])
            server.append(sample['server_ms'])
            database.append(sample['db_ms'])
            application.append(sample['app_ms'])
            queries.append(sample['sql_count'])
        http.sort()
        result.append({
            'operation': name, 'samples': len(samples),
            'p50_ms': statistics.median(http),
            'p95_ms': http[math.ceil(len(http) * 0.95) - 1],
            'max_ms': max(http), 'server_mean_ms': statistics.mean(server),
            'db_mean_ms': statistics.mean(database), 'app_mean_ms': statistics.mean(application),
            'sql_count_mean': statistics.mean(queries),
        })
    return result


def request(client, method, path, expected, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code != expected:
        raise RuntimeError(f'{method} {path}: ожидался {expected}, получен {response.status_code}: {response.text[:200]}')
    return response


def login(client):
    request(client, 'POST', '/login', 303, data={'username': 'staff', 'password': 'demo'})


def create_ticket(client):
    response = request(client, 'POST', '/api/tickets', 201,
                       json={'title': 'Замер', 'body': 'Проверка времени ответа', 'category_id': 1})
    return response.json()['id']


def check_counts(size, before):
    expected = [50, 5, 300, 900]
    if size == 'work':
        expected = [3000, 10, 50000, 150000]
    for table, count in zip(TABLES, expected):
        if before[table] != count:
            raise ValueError(f'Нужно чистое наполнение {size}: {table}={before[table]}, ожидалось {count}. Запустите python -m scripts.seed {size}')


def prepare_request(client, name, method, path):
    kwargs = {}
    if name == 'POST /login':
        request(client, 'POST', '/logout', 303)
        kwargs['data'] = {'username': 'staff', 'password': 'demo'}
    elif name == 'POST /logout':
        login(client)
    elif name == 'POST /api/tickets':
        kwargs['json'] = {'title': 'Замер', 'body': 'Проверка времени ответа', 'category_id': 1}
    elif method == 'PATCH' or name.endswith('/comments'):
        ticket_id = create_ticket(client)
        if method == 'PATCH':
            path = f'/api/tickets/{ticket_id}/status'
            kwargs['json'] = {'status': 'in_progress'}
        else:
            path = f'/api/tickets/{ticket_id}/comments'
            kwargs['json'] = {'body': 'Ответ сотрудника'}
    return path, kwargs


def measure_request(client, operation, i, warmup):
    name, method, path, status = operation
    path, kwargs = prepare_request(client, name, method, path)
    start = time.perf_counter()
    response = request(client, method, path, status, **kwargs)
    http_ms = (time.perf_counter() - start) * 1000
    server_ms = float(response.headers['X-Server-Ms'])
    db_ms = float(response.headers['X-DB-Ms'])
    if db_ms > server_ms:
        raise RuntimeError('Время БД больше серверного времени')
    phase = 'measure'
    if i < warmup:
        phase = 'warmup'
    return {'operation': name, 'phase': phase, 'repeat': i + 1,
            'path': path, 'status': response.status_code, 'http_ms': http_ms,
            'server_ms': server_ms, 'db_ms': db_ms, 'app_ms': server_ms - db_ms,
            'sql_count': int(response.headers['X-SQL-Count'])}


def collect_measurements(url, warmup, repeats, rows):
    with httpx.Client(base_url=url, timeout=120, follow_redirects=False, trust_env=False) as client:
        login(client)
        for operation in OPERATIONS:
            for i in range(warmup + repeats):
                rows.append(measure_request(client, operation, i, warmup))
            login(client)


def save_counts(folder, before, after):
    rows = []
    for name in TABLES:
        rows.append({'table': name, 'before': before[name], 'after': after[name],
                     'added': after[name] - before[name]})
    save_csv(folder / 'counts.csv', rows)
    return rows


def print_results(summary, counts):
    rows = []
    for row in summary:
        rows.append([row['operation'], f"{row['p50_ms']:.3f}", f"{row['p95_ms']:.3f}", f"{row['max_ms']:.3f}"])
    print_table(['Операция', 'p50, мс', 'p95, мс', 'max, мс'], rows)
    rows = []
    for row in counts:
        rows.append([row['table'], row['before'], row['after'], row['added']])
    print_table(['Таблица', 'До', 'После', 'Добавлено'], rows)


def run(size, url, output, warmup, repeats):
    if repeats < 20 or warmup < 1:
        raise ValueError('Нужны минимум 20 повторов и минимум 1 запрос прогрева')
    folder = Path(output) / size
    if folder.exists():
        raise ValueError(f'{folder} уже существует. Для нового прогона задайте другой --output')
    before = counts()
    check_counts(size, before)
    folder.mkdir(parents=True)
    rows = []
    print(f'yaroslav_dementev | {size} | staff | прогрев {warmup} | повторов {repeats}', flush=True)
    try:
        collect_measurements(url, warmup, repeats, rows)
    finally:
        if rows:
            save_csv(folder / 'raw.csv', rows)
    count_rows = save_counts(folder, before, counts())
    summary = summarize(rows)
    save_csv(folder / 'summary.csv', summary)
    print_results(summary, count_rows)


def main():
    parser = argparse.ArgumentParser(description='Замеры чистого наполнения через HTTP; добавляет тестовые заявки и комментарии')
    parser.add_argument('size', choices=['small', 'work'])
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', default='report_data')
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=30)
    args = parser.parse_args()
    run(args.size, args.url, args.output, args.warmup, args.repeats)


if __name__ == '__main__':
    main()
