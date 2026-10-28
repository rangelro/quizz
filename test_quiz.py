import http.server, json, threading, time, urllib.error, urllib.request

import server

server.QUESTIONS = [
    {"q": "A?", "options": ["x", "y", "z", "w"], "answer": 1},
    {"q": "B?", "options": ["x", "y"], "answer": 0, "time": 1},
]
server.TIME_LIMIT = 5

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"


def req(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, raw


def parallel(fn, items):
    out = [None] * len(items)
    def run(i, x): out[i] = fn(x)
    ts = [threading.Thread(target=run, args=(i, x)) for i, x in enumerate(items)]
    for t in ts: t.start()
    for t in ts: t.join()
    return out


def state(pid=None):
    s, j = req("/state" + (f"?id={pid}" if pid else ""))
    assert s == 200, (s, j)
    return j


def sorted_desc(board):
    sc = [b["score"] for b in board]
    return sc == sorted(sc, reverse=True)


# index
with urllib.request.urlopen(base + "/", timeout=10) as r:
    assert r.status == 200

# 60 concurrent joins
names = [f"Player{i}" for i in range(60)]
res = parallel(lambda n: req("/join", {"name": n}), names)
assert all(s == 200 and "id" in j for s, j in res), res
ids = [j["id"] for _, j in res]
st = state()
assert st["phase"] == "lobby" and st["players"] == 60 and len(st["names"]) == 60, st

assert req("/join", {"name": "PLAYER0"})[0] == 400
assert req("/join", {"name": ""})[0] == 400
assert req("/next", {"key": "wrong"})[0] == 403

# question 1
assert req("/next", {"key": server.HOST_KEY})[0] == 200
st = state(ids[0])
assert st["phase"] == "question" and st["n"] == 1 and st["options"] == ["x", "y", "z", "w"], st

choices = [1] * 40 + [0] * 20
res = parallel(lambda a: req("/answer", {"id": a[0], "choice": a[1]}), list(zip(ids, choices)))
assert all(s == 200 for s, _ in res), res
assert req("/answer", {"id": ids[0], "choice": 1})[0] == 400

st = state(ids[0])
assert st["phase"] == "reveal", st
assert st["correct"] == 1 and st["counts"][1] == 40 and sum(st["counts"]) == 60, st
assert len(st["board"]) == 5 and sorted_desc(st["board"]), st["board"]
me = st["me"]
assert me["right"] is True and me["gained"] > 0 and me["rank"] >= 1, me
for pid, c in zip(ids, choices):
    m = state(pid)["me"]
    assert (500 <= m["score"] <= 1000) if c == 1 else m["score"] == 0, m
assert state(ids[59])["me"]["right"] is False

# question 2: timeout
assert req("/next", {"key": server.HOST_KEY})[0] == 200
assert state()["phase"] == "question"
time.sleep(1.2)
assert state()["phase"] == "reveal"
assert req("/answer", {"id": ids[0], "choice": 0})[0] == 400

# end
assert req("/next", {"key": server.HOST_KEY})[0] == 200
st = state(ids[0])
assert st["phase"] == "end", st
assert len(st["board"]) == 10 and sorted_desc(st["board"]), st["board"]
ranks = sorted(state(pid)["me"]["rank"] for pid in ids)
assert ranks[0] == 1 and all(1 <= r <= 60 for r in ranks), ranks

# load: 60 threads x 20 polls
def poll(pid):
    return all(req(f"/state?id={pid}")[0] == 200 for _ in range(20))
t0 = time.time()
assert all(parallel(poll, ids))
dt = time.time() - t0
print(f"1200 /state polls in {dt:.2f}s ({1200 / dt:.0f} req/s)")

srv.shutdown()
print("OK")
