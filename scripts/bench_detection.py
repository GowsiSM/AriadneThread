import time, statistics
from app.synthetic import generate_dataset
from app.graph_engine import TransactionGraph
from app.detection import run_detection

# ---- load dataset the same way main.py does ----
ds = generate_dataset()
transactions = ds.transactions

# Try to find the user_index the server passes to shared_attribute_graph.
# main.py builds it somewhere; check `Select-String -Path .\app\main.py -Pattern "user_index" -Context 2`
user_index = (
    getattr(ds, "user_index", None)
    or getattr(ds, "users_by_id", None)
    or getattr(ds, "users", None)
)
if user_index is None:
    print("ERROR: could not find user_index on dataset; print dir(ds):")
    print([a for a in dir(ds) if not a.startswith("__")])
    raise SystemExit(1)

SCORE_THRESHOLD = 40.0   # matches .env.example default? Check STREAM_TPS line 51 area

def build_graph(n_edges):
    g = TransactionGraph()
    for tx in transactions[:n_edges]:
        g.add_transaction(tx)
    return g

def one_detection_run(g):
    t0 = time.perf_counter()
    directed = g.snapshot()
    shared = g.shared_attribute_graph(user_index)
    _ = run_detection(directed, shared, score_threshold=SCORE_THRESHOLD)
    return time.perf_counter() - t0

def time_at_size(n_edges, reps=5):
    g = build_graph(n_edges)
    times = [one_detection_run(g) for _ in range(reps)]
    med = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    return med, p95

print(f"{'edges':>6}  {'median_ms':>10}  {'p95_ms':>8}")
sizes = [100, 300, 600, 1000, 1282]
med_by_size = {}
for n in sizes:
    med, p95 = time_at_size(n)
    med_by_size[n] = med
    print(f"{n:>6}  {med*1000:>10.1f}  {p95*1000:>8.1f}")

N = 1282
print()
print(f"--- BATCH MODE (1 detection per 30 edges) ---")
batch_total = 0.0
for k in range(1, N // 30 + 1):
    n_edges = k * 30
    if n_edges not in med_by_size:
        med_by_size[n_edges], _ = time_at_size(n_edges, reps=3)
    batch_total += med_by_size[n_edges]
print(f"Batch total (growing graph): {batch_total:.2f} s over {N//30} detection runs")

print()
print(f"--- PER-EDGE MODE (1 detection per edge) ---")
per_edge_total = 0.0
for k in range(1, N + 1):
    n_edges = k
    if n_edges not in med_by_size:
        med_by_size[n_edges], _ = time_at_size(n_edges, reps=1)  # 1 rep to keep runtime sane
    per_edge_total += med_by_size[n_edges]
print(f"Per-edge total (growing graph): {per_edge_total:.2f} s over {N} detection runs")

print()
print(f"Speedup: {per_edge_total / batch_total:.1f}x")
print(f"Sanity check vs stream-bench measurement: 68.7 s")
print(f"Ratio: {batch_total / 68.7:.2f}")
