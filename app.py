import os
import socket
from urllib.parse import unquote, urlparse

from flask import Flask, jsonify, request


STUDENT = "Голенев Антон Андреевич"
GROUP = "БИСТ-23-ПО-3"
MARKER_DEFAULT = "applab"


MARKER = os.environ.get("MARKER", MARKER_DEFAULT)
APP_PORT = int(os.environ.get("APP_PORT", "5000"))


DATABASE_URL = os.environ.get("DATABASE_URL", "")

app = Flask(__name__)
app.json.ensure_ascii = False


def db_params():
    u = urlparse(DATABASE_URL)
    if u.scheme not in ("postgresql", "mysql"):
        raise RuntimeError(
            "DATABASE_URL не задан или схема не postgresql:// и не mysql://")
    return u.scheme, dict(
        host=u.hostname,
        port=u.port or (5432 if u.scheme == "postgresql" else 3306),
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        database=u.path.lstrip("/"),
    )


def connect():
    kind, p = db_params()
    if kind == "postgresql":
        import psycopg2
        p["dbname"] = p.pop("database")
        return kind, psycopg2.connect(connect_timeout=5, **p)
    import MySQLdb
    return kind, MySQLdb.connect(connect_timeout=5, **p)


DDL = {
    "postgresql": "CREATE TABLE IF NOT EXISTS notes ("
                  "id SERIAL PRIMARY KEY, text VARCHAR(200) NOT NULL, "
                  "host VARCHAR(64) NOT NULL, version VARCHAR(32) NOT NULL, "
                  "created TIMESTAMP DEFAULT now())",
    "mysql": "CREATE TABLE IF NOT EXISTS notes ("
             "id INT AUTO_INCREMENT PRIMARY KEY, text VARCHAR(200) NOT NULL, "
             "host VARCHAR(64) NOT NULL, version VARCHAR(32) NOT NULL, "
             "created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
}


def version():


    try:
        with open("/app/VERSION", encoding="utf-8") as f:
            return f.read().strip() or "dev"
    except OSError:
        return "dev"


def describe(e):


    cause = e.__cause__ or e.__context__
    if cause is None or str(cause) in str(e):
        return str(e)
    return "%s (%s)" % (e, cause)


def with_db(action):

    try:
        kind, conn = connect()
    except Exception as e:
        return jsonify(error="нет связи с базой", detail=describe(e)), 503
    try:
        cur = conn.cursor()
        cur.execute(DDL[kind])
        result = action(cur)
        conn.commit()
        return result
    except Exception as e:
        return jsonify(error="ошибка запроса к базе", detail=describe(e)), 503
    finally:
        conn.close()


@app.get("/")
def index():
    return "probe: %s, хост %s\n" % (MARKER, socket.gethostname())


@app.get("/me")
def me():
    try:
        kind, p = db_params()
        database = "%s %s:%s" % (kind, p["host"], p["port"])
    except (RuntimeError, ValueError) as e:

        database = str(e)
    return jsonify(
        student=STUDENT,
        group=GROUP,
        marker=MARKER,
        hostname=socket.gethostname(),
        version=version(),
        database=database,
    )


@app.post("/notes")
def add_note():
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify(error="пустая заметка: передайте -d text=..."), 400

    def insert(cur):

        cur.execute("INSERT INTO notes (text, host, version) VALUES (%s, %s, %s)",
                    (text[:200], socket.gethostname(), version()))
        return jsonify(saved=text[:200], hostname=socket.gethostname(),
                       version=version()), 201

    return with_db(insert)


@app.get("/notes")
def list_notes():
    def select(cur):
        cur.execute("SELECT id, text, host, version, created FROM notes ORDER BY id")
        rows = [dict(id=r[0], text=r[1], host=r[2], version=r[3], created=str(r[4]))
                for r in cur.fetchall()]
        return jsonify(hostname=socket.gethostname(), version=version(),
                       count=len(rows), notes=rows)

    return with_db(select)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT)
