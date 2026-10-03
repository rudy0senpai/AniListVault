import sys, os
print("PYTHONPATH env:", os.environ.get("PYTHONPATH"))
for p in sys.path: print("  path:", p)
