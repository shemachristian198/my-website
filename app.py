from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO, emit
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"
socketio = SocketIO(app)

# ---------------- CONFIG ----------------

UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

online_users = {}

# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

with get_db() as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            profile_image TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()

# ---------------- ROUTES ----------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["username"] = user["username"]
            session["profile"] = user["profile_image"]
            return redirect("/chat")
        else:
            return "Invalid username or password"

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        image = request.files["profile"]

        hashed_password = generate_password_hash(password)

        filename = None
        if image and image.filename != "":
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password, profile_image) VALUES (?,?,?)",
                (username, hashed_password, filename)
            )
            db.commit()
        except:
            return "Username already exists"

        return redirect("/")

    return render_template("register.html")


@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect("/")

    username = session["username"]

    db = get_db()
    messages = db.execute("""
        SELECT * FROM messages
        WHERE sender = ? OR receiver = ?
        ORDER BY timestamp ASC
    """, (username, username)).fetchall()

    return render_template("chat.html", messages=messages)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- SOCKET ----------------

@socketio.on("connect")
def connect():
    username = session.get("username")
    profile = session.get("profile")

    if username:
        online_users[username] = {
            "sid": request.sid,
            "profile": profile
        }

        emit("online_users", [
            {"username": u, "profile": data["profile"]}
            for u, data in online_users.items()
        ], broadcast=True)


@socketio.on("disconnect")
def disconnect():
    username = session.get("username")
    if username in online_users:
        del online_users[username]

        emit("online_users", [
            {"username": u, "profile": data["profile"]}
            for u, data in online_users.items()
        ], broadcast=True)


@socketio.on("private_message")
def private_message(data):
    sender = session["username"]
    receiver = data["to"]
    message = data["message"]

    db = get_db()
    db.execute(
        "INSERT INTO messages (sender, receiver, message) VALUES (?,?,?)",
        (sender, receiver, message)
    )
    db.commit()

    if receiver in online_users:
        emit("receive_private", {
            "from": sender,
            "profile": session.get("profile"),
            "message": message
        }, room=online_users[receiver]["sid"])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

