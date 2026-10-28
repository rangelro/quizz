"""Quiz estilo Kahoot para rede local. Só stdlib: python3 server.py"""
import json, secrets, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8000
TIME_LIMIT = 45
DIR = Path(__file__).parent
QUESTIONS = json.loads((DIR / "questions.json").read_text(encoding="utf-8"))
for _q in QUESTIONS:
    assert 2 <= len(_q["options"]) <= 4, f"2 a 4 opções: {_q['q']}"
    assert 0 <= _q["answer"] < len(_q["options"]), f"resposta inválida: {_q['q']}"
KEY_FILE = DIR / ".host_key"  # chave fixa entre reinícios: aba antiga do apresentador continua valendo
if not KEY_FILE.exists():
    KEY_FILE.write_text(secrets.token_urlsafe(6))
HOST_KEY = KEY_FILE.read_text().strip()
ThreadingHTTPServer.request_queue_size = 128  # padrão é 5: 60 pessoas entrando juntas tomam "connection reset"
lock = threading.Lock()  # ponytail: one global lock, fine for a classroom-sized game
players = {}  # id -> {"name", "score"}
state = {"phase": "lobby", "q": 0, "start": 0.0, "answers": {}}  # answers: id -> (choice, points)


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet sent; just picks the LAN interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


URL = f"http://{lan_ip()}:{PORT}"


def limit():
    return QUESTIONS[state["q"]].get("time", TIME_LIMIT)


def tick():
    if state["phase"] == "question":
        if time.time() - state["start"] >= limit() or (players and len(state["answers"]) >= len(players)):
            state["phase"] = "reveal"


def board(n):
    return sorted(({"name": p["name"], "score": p["score"]} for p in players.values()), key=lambda p: -p["score"])[:n]


def view(pid):
    phase, answers = state["phase"], state["answers"]
    v = {"phase": phase, "n": 0 if phase == "lobby" else state["q"] + 1, "total": len(QUESTIONS),
         "players": len(players), "answered": len(answers), "url": URL}
    q = QUESTIONS[state["q"]] if QUESTIONS else None
    if phase == "lobby":
        v["names"] = [p["name"] for p in players.values()]
    if phase in ("question", "reveal"):
        v["question"], v["options"] = q["q"], q["options"]
    if phase == "question":
        v["remaining"] = max(0.0, limit() - (time.time() - state["start"]))
    if phase == "reveal":
        v["correct"] = q["answer"]
        v["counts"] = [sum(1 for c, _ in answers.values() if c == i) for i in range(len(q["options"]))]
        v["board"] = board(5)
    if phase == "end":
        v["board"] = board(10)
    if pid in players:
        p = players[pid]
        me = v["me"] = {"name": p["name"], "score": p["score"], "answered": pid in answers}
        if phase in ("reveal", "end"):
            me["rank"] = 1 + sum(1 for o in players.values() if o["score"] > p["score"])
        if phase == "reveal":
            choice, pts = answers.get(pid, (None, 0))
            me["gained"], me["right"] = pts, choice == q["answer"]
    return v


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, code, obj=None, body=None, ctype="application/json"):
        body = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            page = DIR / "index.html"
            if not page.exists():
                return self.send(404, {"error": "index.html não encontrado"})
            return self.send(200, body=page.read_bytes(), ctype="text/html")
        if url.path == "/qrcode.min.js":  # lib local (qrcode-generator, MIT): funciona sem internet
            return self.send(200, body=(DIR / "qrcode.min.js").read_bytes(), ctype="text/javascript")
        if url.path == "/state":
            pid = parse_qs(url.query).get("id", [""])[0]
            with lock:
                tick()
                return self.send(200, view(pid))
        self.send(404, {"error": "não encontrado"})

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if size > 10000:
            self.close_connection = True
            return self.send(413, {"error": "corpo grande demais"})
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
            assert isinstance(data, dict)
        except (ValueError, AssertionError):
            return self.send(400, {"error": "JSON inválido"})
        route = {"/join": self.join, "/answer": self.answer, "/next": self.next}.get(urlparse(self.path).path)
        if not route:
            return self.send(404, {"error": "não encontrado"})
        with lock:
            res = route(data)
        self.send(*(res or (200, {"ok": True})))

    def join(self, data):
        name = str(data.get("name", "")).strip()[:12]
        if not name:
            return 400, {"error": "Digite um nome"}
        if any(p["name"].lower() == name.lower() for p in players.values()):
            return 400, {"error": "Esse nome já está em uso"}
        pid = secrets.token_urlsafe(8)
        players[pid] = {"name": name, "score": 0}
        return 200, {"id": pid}

    def answer(self, data):
        tick()
        pid, choice, answers = data.get("id"), data.get("choice"), state["answers"]
        if pid not in players:
            return 400, {"error": "Jogador desconhecido"}
        if state["phase"] != "question":
            return 400, {"error": "Tempo esgotado"}
        if pid in answers:
            return 400, {"error": "Você já respondeu"}
        q = QUESTIONS[state["q"]]
        if type(choice) is not int or not 0 <= choice < len(q["options"]):
            return 400, {"error": "Opção inválida"}
        elapsed = min(time.time() - state["start"], limit())
        pts = round(1000 * (1 - elapsed / limit() / 2)) if choice == q["answer"] else 0
        players[pid]["score"] += pts
        answers[pid] = (choice, pts)
        tick()  # last player in -> reveal right away

    def next(self, data):
        if not secrets.compare_digest(str(data.get("key", "")).encode(), HOST_KEY.encode()):
            return 403, {"error": "Chave do apresentador inválida"}
        phase = state["phase"]
        if phase == "question":
            state["phase"] = "reveal"
        elif phase in ("lobby", "reveal"):
            nq = 0 if phase == "lobby" else state["q"] + 1
            if nq < len(QUESTIONS):
                state.update(phase="question", q=nq, start=time.time(), answers={})
            else:
                state["phase"] = "end"


if __name__ == "__main__":
    print(f"Jogadores, acessem: {URL}")
    print(f"Apresentador (tela grande): http://localhost:{PORT}/?key={HOST_KEY}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
