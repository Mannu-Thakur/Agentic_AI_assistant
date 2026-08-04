import ast, sys

files = [
    r"app\core\redis_client.py",
    r"app\providers\circuit_breaker.py",
    r"app\providers\gemini.py",
    r"app\providers\openrouter.py",
    r"app\services\memory_service.py",
    r"app\agent\nodes.py",
]

ok = True
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        ast.parse(src)
        print(f"OK  {f}")
    except SyntaxError as e:
        print(f"ERR {f}: line {e.lineno}: {e.msg}")
        ok = False

sys.exit(0 if ok else 1)
