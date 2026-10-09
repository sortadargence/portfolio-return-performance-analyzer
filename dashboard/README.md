# Dashboard

See the [project README](../README.md) for installation and a full overview.

From the "Portfolio Return Performance Analyzer" directory, run:

```powershell
.\.venv\Scripts\python.exe dashboard_server.py
```

Then open <http://127.0.0.1:8765>. Use `--port 8766` if that port is already in use. Stop the server with Ctrl+C.

Upload a CSV with columns named `date`, `return`, and `benchmark` (capitalization does not matter). Each row should contain daily decimal returns (`0.01` means 1%). A sample CSV is available in the dashboard.

The dashboard uses only packages already required by `main.py`. Factor analysis downloads Fama–French data, so the first analysis requires an internet connection. CSV contents stay in memory and are sent only to the local server bound to `127.0.0.1`.

The dashboard interface and server were built with GPT-6 Sol and edited by the author. They call the analysis functions in `main.py`. The interface can be redesigned without changing those calculations.
