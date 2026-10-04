import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from app.db import get_db
from app.rules import can_change_status, check_password, reaction

BASE = Path(__file__).parent
PAGE_SIZE = 20
STATUS_NAMES = {'new': 'Новая', 'in_progress': 'В работе', 'closed': 'Закрыта'}

app = FastAPI(title='yaroslav_dementev — служба поддержки')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32), same_site='strict', max_age=28800)
templates = Jinja2Templates(directory=BASE / 'templates')
templates.env.globals['statuses'] = STATUS_NAMES


@app.middleware('http')
async def response_time(request, call_next):
    request.state.timing = {'db_ms': 0, 'queries': 0}
    start = time.perf_counter()
    response = await call_next(request)
    response.headers['X-Server-Ms'] = str((time.perf_counter() - start) * 1000)
    response.headers['X-DB-Ms'] = str(request.state.timing['db_ms'])
    response.headers['X-SQL-Count'] = str(request.state.timing['queries'])
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(HTTPException)
async def handle_error(request, error):
    if error.status_code == 401 and not request.url.path.startswith('/api/'):
        return RedirectResponse('/login', status_code=303)
    return await http_exception_handler(request, error)


def current_user(request: Request, db=Depends(get_db)):
    user_id = request.session.get('user_id')
    user = db.execute('SELECT * FROM users WHERE id = %s', (user_id,)).fetchone()
    if not user:
        request.session.clear()
        raise HTTPException(401, 'Войдите в систему')
    return user


@app.get('/login')
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name='login.html', context={'error': ''})


@app.post('/login')
async def login(request: Request, db=Depends(get_db)):
    form = await request.form()
    request.session.clear()
    user = db.execute('SELECT * FROM users WHERE username = %s', (form.get('username', ''),)).fetchone()
    if not user or not check_password(form.get('password', ''), user['password_hash']):
        return templates.TemplateResponse(request=request, name='login.html', status_code=401,
                                          context={'error': 'Неверный логин или пароль'})
    request.session['user_id'] = user['id']
    return RedirectResponse('/', status_code=303)


@app.post('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login', status_code=303)


class CommentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=10000)


class TicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=10000)
    title: str = Field(min_length=1, max_length=200)
    category_id: int = Field(gt=0)


class StatusInput(BaseModel):
    status: str


def find_ticket(db, ticket_id):
    ticket = db.execute('SELECT * FROM tickets WHERE id = %s', (ticket_id,)).fetchone()
    if not ticket:
        raise HTTPException(404, 'Заявка не найдена')
    return ticket


def categories(db=Depends(get_db)):
    return db.execute('SELECT * FROM categories ORDER BY id').fetchall()


def tickets(page: int = Query(1, ge=1), status=None, db=Depends(get_db)):
    where = ''
    params = []
    if status and status not in STATUS_NAMES:
        raise HTTPException(422, 'Неизвестный статус')
    if status:
        where = ' WHERE t.status = %s'
        params.append(status)
    total = db.execute('SELECT count(*) AS total FROM tickets t' + where, params).fetchone()['total']
    query = '''
        SELECT t.*, c.name AS category, u.username AS author
        FROM tickets t
        JOIN categories c ON c.id = t.category_id
        JOIN users u ON u.id = t.user_id
    '''
    query += where + ' ORDER BY t.id DESC LIMIT %s OFFSET %s'
    params += [PAGE_SIZE, (page - 1) * PAGE_SIZE]
    items = db.execute(query, params).fetchall()
    return {'items': items, 'total': total, 'page': page, 'size': PAGE_SIZE}


@app.post('/api/tickets', status_code=201)
def create_ticket(data: TicketInput, user=Depends(current_user), db=Depends(get_db)):
    if not db.execute('SELECT id FROM categories WHERE id = %s', (data.category_id,)).fetchone():
        raise HTTPException(404, 'Категория не найдена')
    return db.execute('''INSERT INTO tickets (user_id, category_id, title, body)
        VALUES (%s, %s, %s, %s) RETURNING *''',
        (user['id'], data.category_id, data.title, data.body)).fetchone()


def ticket_detail(ticket_id: int, db=Depends(get_db)):
    ticket = find_ticket(db, ticket_id)
    ticket['category'] = db.execute('SELECT * FROM categories WHERE id = %s', (ticket['category_id'],)).fetchone()
    ticket['author'] = db.execute('SELECT id, username FROM users WHERE id = %s', (ticket['user_id'],)).fetchone()
    ticket['comments'] = db.execute('''SELECT c.*, u.username AS author, u.is_staff
        FROM comments c JOIN users u ON u.id = c.user_id
        WHERE c.ticket_id = %s ORDER BY c.created_at, c.id''', (ticket_id,)).fetchall()
    first = None
    for comment in ticket['comments']:
        if comment['is_staff']:
            first = comment['created_at']
            break
    ticket['first_reply_at'] = first
    now = datetime.now(timezone.utc)
    limit = ticket['category']['response_minutes']
    timing = reaction(ticket['created_at'], first, limit, now)
    ticket['reaction_minutes'] = timing['reaction_minutes']
    ticket['overdue'] = timing['overdue']
    return ticket


@app.patch('/api/tickets/{ticket_id}/status')
def change_status(ticket_id: int, data: StatusInput, user=Depends(current_user), db=Depends(get_db)):
    if not user['is_staff']:
        raise HTTPException(403, 'Только для сотрудника')
    ticket = db.execute('SELECT * FROM tickets WHERE id = %s FOR UPDATE', (ticket_id,)).fetchone()
    if not ticket:
        raise HTTPException(404, 'Заявка не найдена')
    if data.status not in STATUS_NAMES:
        raise HTTPException(422, 'Неизвестный статус')
    if not can_change_status(ticket['status'], data.status):
        raise HTTPException(409, 'Недопустимый переход статуса')
    return db.execute('UPDATE tickets SET status = %s WHERE id = %s RETURNING *', (data.status, ticket_id)).fetchone()


@app.post('/api/tickets/{ticket_id}/comments', status_code=201)
def add_comment(ticket_id: int, data: CommentInput, user=Depends(current_user), db=Depends(get_db)):
    ticket = find_ticket(db, ticket_id)
    if not user['is_staff'] and ticket['user_id'] != user['id']:
        raise HTTPException(403, 'Ответить может автор или сотрудник')
    return db.execute('INSERT INTO comments (ticket_id, user_id, body) VALUES (%s, %s, %s) RETURNING *',
                      (ticket_id, user['id'], data.body)).fetchone()


def summary(db=Depends(get_db)):
    rows = db.execute('''SELECT t.id, t.category_id, t.status, t.created_at,
        min(c.created_at) FILTER (WHERE u.is_staff) AS first_reply_at
        FROM tickets t LEFT JOIN comments c ON c.ticket_id = t.id
        LEFT JOIN users u ON u.id = c.user_id GROUP BY t.id''').fetchall()
    groups = categories(db)
    result = {}
    for category in groups:
        category['total'] = 0
        category['open'] = 0
        category['overdue'] = 0
        result[category['id']] = category
    now = datetime.now(timezone.utc)
    for row in rows:
        group = result[row['category_id']]
        group['total'] += 1
        if row['status'] == 'closed':
            continue
        group['open'] += 1
        timing = reaction(row['created_at'], row['first_reply_at'], group['response_minutes'], now)
        if timing['overdue']:
            group['overdue'] += 1
    for group in result.values():
        group['overdue_share'] = 0
        if group['open'] > 0:
            group['overdue_share'] = group['overdue'] / group['open']
    return {'categories': list(result.values()), 'total': len(rows)}


@app.get('/')
def index(request: Request, user=Depends(current_user), data=Depends(tickets), groups=Depends(categories)):
    return templates.TemplateResponse(request=request, name='index.html',
                                      context={'user': user, 'data': data, 'categories': groups})


@app.get('/tickets/{ticket_id}')
def ticket_page(request: Request, user=Depends(current_user), ticket=Depends(ticket_detail)):
    return templates.TemplateResponse(request=request, name='ticket.html', context={'user': user, 'ticket': ticket})


@app.get('/summary')
def summary_page(request: Request, user=Depends(current_user), data=Depends(summary)):
    return templates.TemplateResponse(request=request, name='summary.html', context={'user': user, 'data': data})
