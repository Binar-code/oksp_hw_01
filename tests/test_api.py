from datetime import datetime, timedelta, timezone


def test_authorization(client):
    client.post('/logout')
    response = client.post('/api/tickets', json={'title': 'Тема', 'body': 'Текст', 'category_id': 1})
    assert response.status_code == 401
    assert 'www-authenticate' not in response.headers
    assert client.get('/').url.path == '/login'
    response = client.post('/login', data={'username': 'demo', 'password': 'wrong'})
    assert response.status_code == 401
    assert 'Неверный логин или пароль' in response.text
    assert 'www-authenticate' not in response.headers
    response = client.post('/login', data={'username': 'demo', 'password': 'demo'})
    assert response.status_code == 200 and response.url.path == '/'
    assert client.get('/').status_code == 200
    assert client.get('/api/tickets').status_code == 405
    assert client.get('/api/tickets/1').status_code == 404
    assert client.get('/api/summary').status_code == 404
    cookie = client.cookies.get('session')
    client.cookies.set('session', cookie + 'invalid', domain='testserver.local', path='/')
    assert client.get('/', follow_redirects=False).status_code == 303


def test_create_filter_and_pagination(client, db):
    response = client.post('/api/tickets', json={'title': ' Новая ', 'body': 'Текст', 'category_id': 2})
    assert response.status_code == 201
    ticket = response.json()
    assert ticket['title'] == 'Новая'
    assert ticket['user_id'] == 2 and ticket['status'] == 'new'
    assert {'id', 'created_at', 'body', 'category_id'} <= ticket.keys()
    for i in range(19):
        db.execute("INSERT INTO tickets (user_id, category_id, title, body) VALUES (2, 1, %s, 'Текст')", (f'Заявка {i}',))
    response = client.get('/')
    assert 'text/html' in response.headers['content-type']
    assert 'Найдено: 21' in response.text
    first = response.context['data']
    assert first['total'] == 21 and len(first['items']) == 20 and first['size'] == 20
    assert first['items'][-1]['id'] == ticket['id']
    second = client.get('/?page=2').context['data']
    assert len(second['items']) == 1 and second['items'][0]['id'] == 1
    assert client.get('/?status=').context['data']['total'] == 21
    assert client.get('/?status=').status_code == 200
    assert client.get('/?status=new').context['data']['total'] == 21
    assert client.get('/?status=closed').context['data']['items'] == []
    assert client.get('/?page=999').context['data']['items'] == []


def test_invalid_request(client):
    assert client.get('/?page=0').status_code == 422
    assert client.get('/tickets/999').status_code == 404
    response = client.post('/api/tickets', json={'title': '', 'body': 'Текст', 'category_id': 1})
    assert response.status_code == 422


def test_status_lifecycle(client):
    assert client.patch('/api/tickets/1/status', json={'status': 'in_progress'}).status_code == 403
    client.post('/login', data={'username': 'staff', 'password': 'demo'})
    assert client.patch('/api/tickets/1/status', json={'status': 'closed'}).status_code == 409
    for status in ('in_progress', 'closed'):
        response = client.patch('/api/tickets/1/status', json={'status': status})
        assert response.status_code == 200 and response.json()['status'] == status
    assert client.patch('/api/tickets/1/status', json={'status': 'new'}).status_code == 409


def test_comments_permissions(client):
    assert client.post('/api/tickets/1/comments', json={'body': 'Уточнение'}).status_code == 201
    client.post('/login', data={'username': 'other', 'password': 'demo'})
    assert client.post('/api/tickets/1/comments', json={'body': 'Чужой'}).status_code == 403
    client.post('/login', data={'username': 'staff', 'password': 'demo'})
    assert client.post('/api/tickets/1/comments', json={'body': 'Ответ'}).status_code == 201
    comments = client.get('/tickets/1').context['ticket']['comments']
    assert len(comments) == 2
    assert comments[0]['author'] == 'demo' and comments[1]['is_staff']


def test_first_staff_reply_and_summary(client, db):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for author, minutes in ((2, 5), (1, 30), (1, 90)):
        db.execute('INSERT INTO comments (ticket_id, user_id, body, created_at) VALUES (1, %s, %s, %s)',
                   (author, 'Текст', start + timedelta(minutes=minutes)))
    detail = client.get('/tickets/1').context['ticket']
    assert detail['reaction_minutes'] == 30 and not detail['overdue']
    assert detail['author'] == {'id': 2, 'username': 'demo'}
    assert detail['category']['response_minutes'] == 60
    db.execute("INSERT INTO tickets (user_id, category_id, title, body, status, created_at) VALUES (2, 1, 'Вторая', 'Текст', 'closed', %s)", (start,))
    db.execute("INSERT INTO tickets (user_id, category_id, title, body, status, created_at) VALUES (2, 1, 'Третья', 'Текст', 'in_progress', %s)", (start,))
    response = client.get('/summary')
    assert '50.0%' in response.text
    result = response.context['data']
    assert result['total'] == 3
    category, empty = result['categories']
    assert (category['total'], category['open'], category['overdue'], category['overdue_share']) == (3, 2, 1, 0.5)
    assert empty['overdue_share'] == 0 and empty['total'] == 0
    db.execute("UPDATE tickets SET status = 'closed'")
    category = client.get('/summary').context['data']['categories'][0]
    assert category['total'] == 3
    assert (category['open'], category['overdue'], category['overdue_share']) == (0, 0, 0)
