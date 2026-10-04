import argparse
from datetime import datetime, timedelta, timezone

from app.db import SCHEMA, connect, init_db
from app.rules import hash_password


def seed(size, schema=SCHEMA):
    if size == 'small':
        user_count, category_count, ticket_count = 50, 5, 300
    else:
        user_count, category_count, ticket_count = 3000, 10, 50000

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    password = hash_password('demo', 'yaroslav_dementev_demo')
    init_db(schema)
    with connect(schema) as db:
        db.execute('TRUNCATE comments, tickets, categories, users RESTART IDENTITY')
        for i in range(user_count):
            username = f'user{i + 1}'
            if i == 0:
                username = 'staff'
            elif i == 1:
                username = 'demo'
            db.execute('''
                INSERT INTO users (username, password_hash, is_staff)
                VALUES (%s, %s, %s)
            ''', (username, password, i == 0))

        for i in range(category_count):
            db.execute('''
                INSERT INTO categories (name, response_minutes)
                VALUES (%s, %s)
            ''', (f'Категория {i + 1}', (i + 1) * 30))

        statuses = ['new', 'in_progress', 'closed']
        for i in range(ticket_count):
            author = 2 + i % (user_count - 1)
            category = i % category_count
            status = statuses[i % 3]
            created = start + timedelta(minutes=i + 1)
            db.execute('''INSERT INTO tickets (user_id, category_id, title, body, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)''',
                (author, category + 1, f'Заявка {i + 1}', f'Описание проблемы {i + 1}', status, created))
            delay = (category + 1) * 30
            if i % 2 == 0:
                delay += 10
            else:
                delay -= 10
            for j in range(3):
                comment_author = author
                comment_time = created + timedelta(minutes=j)
                if status != 'new' and j > 0:
                    comment_author = 1
                    comment_time = created + timedelta(minutes=delay + j)
                db.execute('''
                    INSERT INTO comments (ticket_id, user_id, body, created_at)
                    VALUES (%s, %s, %s, %s)
                ''', (i + 1, comment_author,
                      f'Комментарий {j + 1} к заявке {i + 1}', comment_time))

        for table in ('users', 'categories', 'tickets', 'comments'):
            count = db.execute(f'SELECT count(*) AS count FROM {table}').fetchone()['count']
            print(f'{schema}.{table}: {count}')


def main():
    parser = argparse.ArgumentParser(description='Заменяет все данные выбранным наполнением')
    parser.add_argument('size', choices=['small', 'work'])
    seed(parser.parse_args().size)


if __name__ == '__main__':
    main()
