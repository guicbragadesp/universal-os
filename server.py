"""Universal OS — Python 3.10+, banco central SQLite, sem dependências externas."""
import argparse
from contextlib import contextmanager
import datetime as dt
import hashlib
import hmac
import http.cookies
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('OS_DATA_DIR', str(ROOT / 'data'))).resolve()
DB = DATA / 'universal.sqlite3'
DATABASE_LOCK = threading.RLock()
HTTPS = os.environ.get('OS_HTTPS', '0') == '1'
SETUP_TOKEN = os.environ.get('OS_SETUP_TOKEN') or secrets.token_urlsafe(24)
DEFAULTS = ['TRANSFERÊNCIA', 'LICENCIAMENTO', 'IPVA', 'SEGURO', 'PLACA MERCOSUL', 'LAUDO DE VISTORIA', 'HONORÁRIO']

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

@contextmanager
def connect(database=None):
    with DATABASE_LOCK:
        c = sqlite3.connect(database or DB, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

def initialize(database=None):
    DATA.mkdir(parents=True, exist_ok=True)
    with connect(database) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), next_number INTEGER NOT NULL);
        INSERT OR IGNORE INTO settings VALUES(1,40952);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, number INTEGER UNIQUE NOT NULL,
          request_key TEXT UNIQUE NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL,
          vehicle TEXT NOT NULL, plate TEXT NOT NULL, items TEXT NOT NULL, paid INTEGER NOT NULL,
          total INTEGER NOT NULL, notes TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
          created_by INTEGER REFERENCES users(id), updated_by INTEGER REFERENCES users(id),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS orders_plate ON orders(plate);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
          actor INTEGER REFERENCES users(id), action TEXT NOT NULL, at TEXT NOT NULL, snapshot TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS recovery(user_id INTEGER PRIMARY KEY REFERENCES users(id),
          token_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')
        columns = {row['name'] for row in c.execute('PRAGMA table_info(orders)')}
        if 'paid_stamp' not in columns:
            c.execute('ALTER TABLE orders ADD COLUMN paid_stamp INTEGER NOT NULL DEFAULT 0')
        if 'payment_confirmed_by' not in columns:
            c.execute('ALTER TABLE orders ADD COLUMN payment_confirmed_by INTEGER REFERENCES users(id)')
        if 'payment_confirmed_at' not in columns:
            c.execute('ALTER TABLE orders ADD COLUMN payment_confirmed_at TEXT')

def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return salt + ':' + digest

def password_ok(password, stored):
    salt, digest = stored.split(':')
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex(), digest)

def text_field(data, key, maximum=200, required=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value.strip()) > maximum:
        raise ValueError('Campo inválido: ' + key)
    value = value.strip()
    if required and not value:
        raise ValueError('Preencha o campo ' + key + '.')
    return value

def user_fields(data):
    username = text_field(data, 'username', 40, True).lower()
    if not re.fullmatch(r'[a-z0-9._-]{3,40}', username):
        raise ValueError('Usuário: use 3 a 40 letras sem acento, números, ponto ou traço.')
    name = text_field(data, 'name', 100, True)
    password = text_field(data, 'password', 200, True)
    if not 4 <= len(password) <= 10:
        raise ValueError('A senha precisa ter de 4 a 10 caracteres.')
    return username, name, password

def cents(value):
    if type(value) is not int or value < 0 or value > 10000000000:
        raise ValueError('Informe um valor válido, com até duas casas decimais.')
    return value

def order_fields(data):
    date = text_field(data, 'date', 10, True)
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise ValueError('Data inválida.')
    plate = re.sub(r'[-\s]', '', text_field(data, 'plate', 12)).upper()
    if plate and not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}', plate):
        raise ValueError('Placa inválida. Exemplo: ABC1234 ou ABC1D23.')
    raw = data.get('items')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 500:
        raise ValueError('Adicione entre 1 e 500 serviços.')
    items = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Serviço inválido.')
        items.append({'description': text_field(item, 'description', 150, True), 'value': cents(item.get('value'))})
    total = sum(x['value'] for x in items)
    paid = cents(data.get('paid', 0))
    if paid > total:
        raise ValueError('O pagamento não pode ser maior que o total da OS.')
    paid_stamp = data.get('paid_stamp', False)
    if type(paid_stamp) is not bool:
        raise ValueError('Opção de carimbo inválida.')
    if paid_stamp and (paid != total or total == 0):
        raise ValueError('O carimbo PAGO exige uma OS com valor e saldo zerado.')
    return {'paid_stamp': int(paid_stamp), 'date': date, 'name': text_field(data, 'name', 150, True), 'phone': text_field(data, 'phone', 60),
            'vehicle': text_field(data, 'vehicle', 150), 'plate': plate, 'items': items,
            'paid': paid, 'total': total, 'notes': text_field(data, 'notes', 3000)}

def order_json(row):
    value = dict(row)
    value['items'] = json.loads(value['items'])
    value['balance'] = value['total'] - value['paid']
    value['payment_confirmed'] = bool(value.get('payment_confirmed_by') and value.get('payment_confirmed_at')
                                      and value['total'] > 0 and value['paid'] == value['total'])
    value.pop('request_key', None)
    return value

ORDER_SELECT = '''SELECT o.*, c.name AS created_name, u.name AS updated_name, a.name AS payment_confirmed_name FROM orders o
                  JOIN users c ON c.id=o.created_by JOIN users u ON u.id=o.updated_by
                  LEFT JOIN users a ON a.id=o.payment_confirmed_by'''

class Handler(BaseHTTPRequestHandler):
    server_version = 'UniversalOS'

    def log_message(self, fmt, *args):
        # Never log paths, credentials or client data.
        pass

    def send(self, value, code=200, cookie=None, filename=None):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(body)

    def payload(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 300000:
            raise ValueError('Requisição inválida ou muito grande.')
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise ValueError('Formato de requisição inválido.')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError('Requisição inválida.')
        return value

    def identity(self, c):
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie.get('universal_session')
            if not token:
                return None
            hashed = hashlib.sha256(token.value.encode()).hexdigest()
            return c.execute('''SELECT u.id,u.username,u.name,u.admin,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token=? AND s.expires>? AND u.active=1''', (hashed, time.time())).fetchone()
        except http.cookies.CookieError:
            return None

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if not path.startswith('/api/'):
                return self.static(path)
            with connect() as c:
                user = self.identity(c)
                if path == '/api/session':
                    setup = c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
                    return self.send({'user': dict(user) if user else None, 'setup': setup, 'defaults': DEFAULTS})
                if not user:
                    return self.send({'error': 'Entre com seu usuário e senha.'}, 401)
                if path == '/api/orders':
                    query = parse_qs(urlsplit(self.path).query)
                    q = query.get('q', [''])[0].strip()[:100]
                    page = max(1, min(100000, int(query.get('page', ['1'])[0])))
                    plate = re.sub(r'[-\s]', '', q).upper()
                    where = ' WHERE (?="" OR CAST(o.number AS TEXT)=? OR o.plate LIKE ? OR o.name LIKE ?)'
                    if query.get('payment_review', [''])[0] == 'pending':
                        where += ' AND o.total>0 AND o.paid=o.total AND o.payment_confirmed_by IS NULL'
                    args = (q, q, '%' + plate + '%', '%' + q + '%')
                    rows = c.execute(ORDER_SELECT + where + ' ORDER BY o.number DESC LIMIT 50 OFFSET ?', (*args, (page-1)*50)).fetchall()
                    count = c.execute('SELECT COUNT(*) FROM orders o' + where, args).fetchone()[0]
                    stats = c.execute('SELECT COUNT(*) count,COALESCE(SUM(total),0) total,COALESCE(SUM(total-paid),0) balance FROM orders').fetchone()
                    return self.send({'orders': [order_json(r) for r in rows], 'count': count, 'page': page,
                        'stats': dict(stats), 'next_number': c.execute('SELECT next_number FROM settings').fetchone()[0]})
                match = re.fullmatch(r'/api/orders/(\d+)', path)
                if match:
                    row = c.execute(ORDER_SELECT + ' WHERE o.id=?', (int(match[1]),)).fetchone()
                    if not row:
                        return self.send({'error': 'OS não encontrada.'}, 404)
                    history = [dict(x) for x in c.execute('SELECT a.action,a.at,u.name FROM audit a JOIN users u ON u.id=a.actor WHERE a.order_id=? ORDER BY a.id DESC', (row['id'],))]
                    return self.send({'order': order_json(row), 'history': history})
                if not user['admin']:
                    return self.send({'error': 'Somente o administrador tem acesso.'}, 403)
                if path == '/api/users':
                    return self.send({'users': [dict(x) for x in c.execute('SELECT id,username,name,admin,active FROM users ORDER BY name')]})
                if path == '/api/backup':
                    # One read transaction provides a consistent snapshot; excludes passwords and sessions.
                    c.execute('BEGIN')
                    backup = {'format': 'universal-os-v1', 'exported_at': now(),
                        'next_number': c.execute('SELECT next_number FROM settings').fetchone()[0],
                        'users': [dict(x) for x in c.execute('SELECT id,username,name,admin,active,created_at FROM users')],
                        'orders': [order_json(x) for x in c.execute(ORDER_SELECT + ' ORDER BY o.number')],
                        'audit': [dict(x) for x in c.execute('SELECT * FROM audit ORDER BY id')]}
                    return self.send(backup, filename='Universal-OS-registros-' + dt.date.today().isoformat() + '.json')
                return self.send({'error': 'Não encontrado.'}, 404)
        except (ValueError, json.JSONDecodeError) as e:
            self.send({'error': str(e)}, 400)
        except Exception:
            self.send({'error': 'Não foi possível concluir a operação. Tente novamente.'}, 500)

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            data = self.payload()
            # Reject cross-origin JSON even if a client can otherwise construct it.
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                return self.send({'error': 'Origem não autorizada.'}, 403)
            with connect() as c:
                if path == '/api/setup':
                    if not hmac.compare_digest(str(data.get('token', '')), SETUP_TOKEN):
                        return self.send({'error': 'Código de configuração inválido.'}, 403)
                    username, name, password = user_fields(data)
                    hashed = password_hash(password)
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                        return self.send({'error': 'O administrador já foi configurado.'}, 409)
                    c.execute('INSERT INTO users(username,name,password,admin,created_at) VALUES(?,?,?,1,?)', (username, name, hashed, now()))
                    return self.send({'ok': True}, 201)
                if path == '/api/recover':
                    username = text_field(data, 'username', 40).lower()
                    code = text_field(data, 'code', 100)
                    password = text_field(data, 'password', 200, True)
                    if not 4 <= len(password) <= 10:
                        raise ValueError('Use de 4 a 10 caracteres na nova senha.')
                    key = self.client_address[0] + ':recovery'
                    c.execute('BEGIN IMMEDIATE')
                    attempt = c.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
                    if attempt and attempt['failures'] >= 8 and attempt['until'] > time.time():
                        return self.send({'error': 'Muitas tentativas. Aguarde 15 minutos.'}, 429)
                    row = c.execute('''SELECT u.id,r.token_hash FROM users u JOIN recovery r ON r.user_id=u.id
                        WHERE u.username=? AND u.active=1 AND u.admin=1''', (username,)).fetchone()
                    valid = hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), row['token_hash'] if row else '0'*64)
                    if not row or not valid:
                        failures = attempt['failures']+1 if attempt and attempt['until'] > time.time() else 1
                        c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (key, failures, time.time()+900))
                        return self.send({'error': 'Usuário ou código de recuperação inválido.'}, 400)
                    c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password), row['id']))
                    c.execute('DELETE FROM recovery WHERE user_id=?', (row['id'],))
                    c.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
                    c.execute('DELETE FROM login_attempts WHERE key IN (?,?)', (key, self.client_address[0]+':'+username))
                    c.execute('INSERT INTO audit(actor,action,at,snapshot) VALUES(?,?,?,?)', (row['id'], 'recuperou a própria senha', now(), '{}'))
                    return self.send({'ok': True})
                if path == '/api/login':
                    username = text_field(data, 'username', 40).lower()
                    password = text_field(data, 'password', 200)
                    key = self.client_address[0] + ':' + username
                    attempt = c.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
                    if attempt and attempt['failures'] >= 8 and attempt['until'] > time.time():
                        return self.send({'error': 'Muitas tentativas. Aguarde 15 minutos.'}, 429)
                    row = c.execute('SELECT * FROM users WHERE username=? AND active=1', (username,)).fetchone()
                    # Execute the same expensive hash when username is unknown.
                    stored = row['password'] if row else '00'*16 + ':' + '00'*32
                    valid = password_ok(password, stored)
                    if not row or not valid:
                        failures = attempt['failures']+1 if attempt and attempt['until'] > time.time() else 1
                        c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (key, failures, time.time()+900))
                        return self.send({'error': 'Usuário ou senha incorretos.'}, 401)
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    c.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
                    c.execute('DELETE FROM login_attempts WHERE key=?', (key,))
                    c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], csrf, time.time()+8*3600))
                    cookie = 'universal_session=' + token + '; Path=/; HttpOnly; SameSite=Strict' + ('; Secure' if HTTPS else '')
                    return self.send({'ok': True}, cookie=cookie)
                user = self.identity(c)
                if not user:
                    return self.send({'error': 'Sua sessão terminou. Entre novamente.'}, 401)
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), user['csrf']):
                    return self.send({'error': 'Atualize a página e tente novamente.'}, 403)
                if path == '/api/logout':
                    c.execute('DELETE FROM sessions WHERE user_id=? AND csrf=?', (user['id'], user['csrf']))
                    return self.send({'ok': True}, cookie='universal_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
                if path == '/api/password':
                    row = c.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()
                    if not password_ok(text_field(data, 'current', 200), row['password']):
                        return self.send({'error': 'Senha atual incorreta.'}, 400)
                    new = text_field(data, 'password', 200, True)
                    if not 4 <= len(new) <= 10:
                        raise ValueError('Use de 4 a 10 caracteres.')
                    c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(new), user['id']))
                    c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                    return self.send({'ok': True})
                if path == '/api/recovery-code':
                    if not user['admin']:
                        return self.send({'error': 'Somente o administrador tem acesso.'}, 403)
                    c.execute('BEGIN IMMEDIATE')
                    row = c.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()
                    if not password_ok(text_field(data, 'current', 200), row['password']):
                        return self.send({'error': 'Senha atual incorreta.'}, 400)
                    code = secrets.token_urlsafe(32)
                    c.execute('INSERT OR REPLACE INTO recovery VALUES(?,?,?)', (user['id'], hashlib.sha256(code.encode()).hexdigest(), now()))
                    c.execute('INSERT INTO audit(actor,action,at,snapshot) VALUES(?,?,?,?)', (user['id'], 'gerou código de recuperação', now(), '{}'))
                    return self.send({'code': code, 'username': user['username']})
                if path == '/api/orders':
                    values = order_fields(data)
                    key = text_field(data, 'request_key', 100, True)
                    if not re.fullmatch('[a-zA-Z0-9_-]{16,100}', key):
                        raise ValueError('Identificador da requisição inválido.')
                    c.execute('BEGIN IMMEDIATE')
                    existing = c.execute('SELECT id FROM orders WHERE request_key=?', (key,)).fetchone()
                    if existing:
                        return self.send({'id': existing['id'], 'reused': True})
                    number = c.execute('SELECT next_number FROM settings').fetchone()[0]
                    stamp = now()
                    cur = c.execute('''INSERT INTO orders(number,request_key,date,name,phone,vehicle,plate,items,paid,total,notes,created_by,updated_by,created_at,updated_at,paid_stamp)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (number, key, values['date'], values['name'], values['phone'], values['vehicle'], values['plate'],
                        json.dumps(values['items'], ensure_ascii=False), values['paid'], values['total'], values['notes'], user['id'], user['id'], stamp, stamp, values['paid_stamp']))
                    c.execute('UPDATE settings SET next_number=? WHERE id=1', (number+1,))
                    c.execute('INSERT INTO audit(order_id,actor,action,at,snapshot) VALUES(?,?,?,?,?)', (cur.lastrowid, user['id'], 'criou', stamp, json.dumps(values, ensure_ascii=False)))
                    return self.send({'id': cur.lastrowid, 'number': number}, 201)
                match = re.fullmatch(r'/api/orders/(\d+)/(confirm-payment|reopen-payment-review)', path)
                if match:
                    if not user['admin']:
                        return self.send({'error': 'Somente a gerência, com acesso de administrador, pode conferir recebimentos.'}, 403)
                    c.execute('BEGIN IMMEDIATE')
                    row = c.execute('SELECT * FROM orders WHERE id=?', (int(match[1]),)).fetchone()
                    if not row:
                        return self.send({'error': 'OS não encontrada.'}, 404)
                    if type(data.get('version')) is not int or data['version'] != row['version']:
                        return self.send({'error': 'A OS mudou. Reabra e confira os valores antes de confirmar.'}, 409)
                    confirm = match[2] == 'confirm-payment'
                    if confirm and (row['total'] <= 0 or row['paid'] != row['total']):
                        return self.send({'error': 'A confirmação final exige pagamento informado igual ao total da OS.'}, 400)
                    if bool(row['payment_confirmed_by']) == confirm:
                        return self.send({'id': row['id'], 'ok': True})
                    stamp = now()
                    c.execute('''UPDATE orders SET payment_confirmed_by=?,payment_confirmed_at=?,
                        updated_by=?,updated_at=?,version=version+1 WHERE id=?''',
                        (user['id'] if confirm else None, stamp if confirm else None, user['id'], stamp, row['id']))
                    action = 'confirmou o recebimento' if confirm else 'reabriu a conferência do recebimento'
                    snapshot = {'paid': row['paid'], 'total': row['total'], 'previous_version': row['version']}
                    c.execute('INSERT INTO audit(order_id,actor,action,at,snapshot) VALUES(?,?,?,?,?)',
                              (row['id'], user['id'], action, stamp, json.dumps(snapshot)))
                    return self.send({'id': row['id'], 'ok': True})
                match = re.fullmatch(r'/api/orders/(\d+)', path)
                if match:
                    values = order_fields(data)
                    c.execute('BEGIN IMMEDIATE')
                    row = c.execute('SELECT * FROM orders WHERE id=?', (int(match[1]),)).fetchone()
                    if not row:
                        return self.send({'error': 'OS não encontrada.'}, 404)
                    if data.get('version') != row['version']:
                        return self.send({'error': 'Outro usuário alterou esta OS. Reabra a OS para carregar a versão atual.'}, 409)
                    stamp = now()
                    financial_changed = values['total'] != row['total'] or values['paid'] != row['paid'] or values['items'] != json.loads(row['items'])
                    confirmed_by = None if financial_changed else row['payment_confirmed_by']
                    confirmed_at = None if financial_changed else row['payment_confirmed_at']
                    c.execute('''UPDATE orders SET date=?,name=?,phone=?,vehicle=?,plate=?,items=?,paid=?,total=?,notes=?,updated_by=?,updated_at=?,paid_stamp=?,payment_confirmed_by=?,payment_confirmed_at=?,version=version+1 WHERE id=?''',
                        (values['date'],values['name'],values['phone'],values['vehicle'],values['plate'],json.dumps(values['items'],ensure_ascii=False),values['paid'],values['total'],values['notes'],user['id'],stamp,values['paid_stamp'],confirmed_by,confirmed_at,row['id']))
                    action = 'alterou valores ou serviços e reabriu a conferência' if financial_changed and row['payment_confirmed_by'] else 'alterou'
                    c.execute('INSERT INTO audit(order_id,actor,action,at,snapshot) VALUES(?,?,?,?,?)', (row['id'],user['id'],action,stamp,json.dumps(values,ensure_ascii=False)))
                    return self.send({'id': row['id'], 'number': row['number']})
                if not user['admin']:
                    return self.send({'error': 'Somente o administrador tem acesso.'}, 403)
                if path == '/api/sequence':
                    number = data.get('next_number')
                    if type(number) is not int or not 1 <= number <= 999999999:
                        raise ValueError('Informe um número entre 1 e 999999999.')
                    c.execute('BEGIN IMMEDIATE')
                    maximum = c.execute('SELECT COALESCE(MAX(number),0) FROM orders').fetchone()[0]
                    if number <= maximum:
                        raise ValueError('O próximo número precisa ser maior que ' + str(maximum) + ', para não repetir OS já cadastradas.')
                    previous = c.execute('SELECT next_number FROM settings').fetchone()[0]
                    c.execute('UPDATE settings SET next_number=? WHERE id=1', (number,))
                    c.execute('INSERT INTO audit(actor,action,at,snapshot) VALUES(?,?,?,?)', (user['id'],'alterou numeração',now(),json.dumps({'previous':previous,'next':number})))
                    return self.send({'ok': True})
                if path == '/api/users':
                    username,name,password = user_fields(data)
                    admin = 1 if data.get('admin') is True else 0
                    try:
                        c.execute('INSERT INTO users(username,name,password,admin,created_at) VALUES(?,?,?,?,?)', (username,name,password_hash(password),admin,now()))
                    except sqlite3.IntegrityError:
                        return self.send({'error': 'Este usuário já existe.'}, 409)
                    return self.send({'ok': True}, 201)
                match = re.fullmatch(r'/api/users/(\d+)', path)
                if match:
                    uid = int(match[1])
                    if uid == user['id']:
                        raise ValueError('Use a opção Minha senha para alterar seu acesso.')
                    row = c.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone()
                    if not row:
                        return self.send({'error': 'Usuário não encontrado.'}, 404)
                    if 'active' in data:
                        c.execute('UPDATE users SET active=? WHERE id=?', (1 if data['active'] is True else 0, uid))
                    if data.get('password'):
                        password = text_field(data, 'password', 200, True)
                        if not 4 <= len(password) <= 10:
                            raise ValueError('Use de 4 a 10 caracteres.')
                        c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password),uid))
                    c.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                    return self.send({'ok': True})
                return self.send({'error': 'Não encontrado.'}, 404)
        except (ValueError, json.JSONDecodeError) as e:
            self.send({'error': str(e)}, 400)
        except sqlite3.IntegrityError:
            self.send({'error': 'Conflito ao salvar. Atualize a página e tente novamente.'}, 409)
        except Exception:
            self.send({'error': 'Não foi possível salvar. Confira a conexão e tente novamente.'}, 500)

    def static(self, path):
        files = {'/favicon.ico': ('icon.ico','image/x-icon'), '/': ('index.html','text/html; charset=utf-8'), '/app.js': ('app.js','text/javascript; charset=utf-8'), '/style.css': ('style.css','text/css; charset=utf-8')}
        if path not in files:
            self.send_error(404)
            return
        name, mime = files[path]
        body = (ROOT / 'public' / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header('Referrer-Policy','same-origin')
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    initialize()
    with connect() as c:
        first = c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    print('Universal OS — http://' + args.host + ':' + str(args.port), flush=True)
    if first:
        print('Código para criar o primeiro administrador: ' + SETUP_TOKEN, flush=True)
    ThreadingHTTPServer((args.host,args.port), Handler).serve_forever()
