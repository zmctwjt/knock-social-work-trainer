import os

ROOT = "deliverables/backend"
SKIP = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "alembic/versions_tmp"}
buckets = {"app": [0, 0], "tests": [0, 0], "scripts": [0, 0], "alembic": [0, 0]}
total = [0, 0]
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
    for name in filenames:
        if not name.endswith(".py"):
            continue
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, ROOT).replace("\\", "/")
        bucket = rel.split("/")[0] if "/" in rel else "root"
        lines = sum(1 for _ in open(full, encoding="utf-8"))
        if bucket in buckets:
            buckets[bucket][0] += 1
            buckets[bucket][1] += lines
        total[0] += 1
        total[1] += lines
for key, (count, lines) in buckets.items():
    print(f"{key}: {count} files, {lines} lines")
print(f"total: {total[0]} py files, {total[1]} lines")
