import argparse
import os
import time
from pathlib import Path

import psycopg
from fastapi import Request
from psycopg import sql
from psycopg.rows import dict_row

SCHEMA = os.environ.get('DB_SCHEMA', 'yaroslav_dementev')


def connect(schema=SCHEMA):
    return psycopg.connect(options=f'-c search_path={schema}', row_factory=dict_row)


class MeasuredDB:
    def __init__(self, conn, timing):
        self.conn = conn
        self.timing = timing

    def execute(self, query, params=None):
        start = time.perf_counter()
        try:
            return self.conn.execute(query, params)
        finally:
            self.timing['db_ms'] += (time.perf_counter() - start) * 1000
            self.timing['queries'] += 1


def get_db(request: Request):
    with connect() as conn:
        yield MeasuredDB(conn, request.state.timing)


def init_db(schema=SCHEMA, reset=False):
    with connect(schema) as conn:
        if reset:
            conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        conn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
        conn.execute(Path(__file__).with_name('schema.sql').read_text())


def main():
    parser = argparse.ArgumentParser(description='Создание схемы базы данных')
    parser.add_argument('--reset', action='store_true', help='Удалить все данные и заново создать таблицы')
    init_db(reset=parser.parse_args().reset)


if __name__ == '__main__':
    main()
