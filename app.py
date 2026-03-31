from flask import Flask, render_template, session
from flask_socketio import SocketIO, emit, join_room
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'obshiy-chat-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

DB = 'chat.db'

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        nick TEXT PRIMARY KEY,
        password TEXT,
        verified INTEGER DEFAULT 0,
        is_dev INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT,
        nick TEXT,
        text TEXT,
        time TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO users (nick, password, verified, is_dev) VALUES ('droidYn', '112112', 1, 1)")
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

# ====================== АУТЕНТИФИКАЦИЯ ======================
@socketio.on('register')
def handle_register(data):
    nick = data['nick'].strip()
    pwd = data['password']
    conn = get_db()
    c = conn.cursor()
    if c.execute("SELECT nick FROM users WHERE nick=?", (nick,)).fetchone():
        emit('error', {'msg': 'Этот ник уже занят'})
        conn.close()
        return
    c.execute("INSERT INTO users (nick, password) VALUES (?, ?)", (nick, pwd))
    conn.commit()
    conn.close()
    emit('register_ok')

@socketio.on('login')
def handle_login(data):
    nick = data['nick'].strip()
    pwd = data['password']
    conn = get_db()
    c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE nick=? AND password=?", (nick, pwd)).fetchone()
    conn.close()
    if not user:
        emit('error', {'msg': 'Неверный ник или пароль'})
        return
    if user['banned']:
        emit('banned')
        return
    session['nick'] = nick
    emit('login_ok', {
        'nick': nick,
        'verified': bool(user['verified']),
        'is_dev': bool(user['is_dev'])
    })

# ====================== ЧАТЫ ======================
@socketio.on('join_room')
def join_room_event(data):
    room = data['room']
    nick = data['nick']
    join_room(room)
    if room == 'general':
        emit('new_message', {'nick': 'system', 'text': f'{nick} в чате', 'time': datetime.now().strftime("%H:%M")}, room=room)

@socketio.on('send_message')
def send_message(data):
    room = data['room']
    nick = data['nick']
    text = data['text'].strip()
    if not text: return
    time_str = datetime.now().strftime("%H:%M")

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO messages (room, nick, text, time) VALUES (?, ?, ?, ?)", (room, nick, text, time_str))
    conn.commit()
    conn.close()

    conn = get_db()
    u = conn.execute("SELECT verified, is_dev FROM users WHERE nick=?", (nick,)).fetchone()
    conn.close()

    msg = {
        'nick': nick,
        'text': text,
        'time': time_str,
        'verified': bool(u['verified']) if u else False,
        'is_dev': bool(u['is_dev']) if u else False
    }
    emit('new_message', msg, room=room)

@socketio.on('get_messages')
def get_messages(data):
    room = data['room']
    conn = get_db()
    msgs = conn.execute("SELECT nick, text, time FROM messages WHERE room=? ORDER BY id", (room,)).fetchall()
    conn.close()
    emit('messages_list', [dict(m) for m in msgs])

# ====================== АДМИН ======================
@socketio.on('get_all_users')
def get_all_users(data):
    if data['nick'] != 'droidYn': return
    conn = get_db()
    users = conn.execute("SELECT nick, verified, banned FROM users").fetchall()
    conn.close()
    emit('users_list', [dict(u) for u in users])

@socketio.on('toggle_verify')
def toggle_verify(data):
    if data['admin'] != 'droidYn': return
    target = data['target']
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET verified = NOT verified WHERE nick=?", (target,))
    verified = c.execute("SELECT verified FROM users WHERE nick=?", (target,)).fetchone()['verified']
    conn.commit()
    conn.close()
    msg = "Здравствуйте! Разработчик Общего чата droidYn выдал вам официальную верификацию." if verified else "Ваша верификация снята."
    emit('new_notification', {'text': msg, 'time': datetime.now().strftime("%H:%M")}, room=target)

@socketio.on('ban_user')
def ban_user(data):
    if data['admin'] != 'droidYn': return
    target = data['target']
    conn = get_db()
    conn.execute("UPDATE users SET banned=1 WHERE nick=?", (target,))
    conn.commit()
    conn.close()
    emit('new_notification', {'text': 'Вас заблокировали в Общем чате, вас выкинет с аккаунта через 30 секунд.', 'time': datetime.now().strftime("%H:%M")}, room=target)
    emit('force_ban', room=target)

@socketio.on('restart_all')
def restart_all(data):
    if data['nick'] == 'droidYn':
        emit('force_restart', {}, broadcast=True)

if __name__ == '__main__':
    print("🚀 Общий чат запущен — http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)