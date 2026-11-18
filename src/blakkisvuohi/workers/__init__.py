"""
Running on Cloudflare Workers (Python, Pyodide): the entry point is src/worker.py.

runtime.py is plain Python and tested like the rest. d1.py and session.py talk to the JavaScript
side (the D1 binding, fetch) and only work inside a Worker.
"""
