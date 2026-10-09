# Portfolio Return Performance Analyzer

This project reads daily portfolio and benchmark returns from a csv file and summarize key performance and risk metrics, as well as factor exposures.
## Requirements

- Python 3.13 (the version used to verify this project)
- An internet connection when running the analysis, because factor data is downloaded from [Kenneth French's Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) through `pandas-datareader`

Install the four Python packages listed in [requirements.txt](requirements.txt). The dashboard itself uses the Python standard library and has no JavaScript build step.

## Dashboard

The repository includes a dashboard. While the analysis can be run as a CLI application, the dashboard is a great tool to visualize the different metrics calculated.

To initialize the dashboard:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe dashboard_server.py
```

Open <http://127.0.0.1:8765> in your browser. Stop the server with Ctrl+C. If port 8765 is busy, run `dashboard_server.py --port 8766` and open that port instead.

On macOS or Linux, use `python3 -m venv .venv`, then `.venv/bin/python` in place of `.\.venv\Scripts\python.exe` in the commands above.

## Return CSV Format

Use columns named `date`, `return`, and `benchmark`; capitalization does not matter. Upload daily returns in decimal values (`0.01` means 1%). For example:

```csv
date,return,benchmark
2024-01-02,0.010,0.008
2024-01-03,-0.005,-0.003
```

The loader sorts dates, drops rows with missing or invalid dates or returns, and rejects duplicate dates. The dashboard accepts CSV files up to 10 MiB and 20,000 valid rows. It needs at least the greater of 30 rows and the selected rolling-window length (20–252 days).

The **Try sample data** button loads [returns.csv](returns.csv), which contains the daily returns of Invesco QQQ Trust (QQQ) downloaded from the yfinance library over 6,036 observations (Jan 3, 2001 — Dec 31, 2024). 

## Report

The report shows the following metrics:
- Portfolio and benchmark return, volatility, Sharpe ratio, Sortino ratio, and maximum drawdown
- Growth of $1 invested in the portfolio at the beggining of the period, drawdown, rolling Sharpe ratio, and daily return distribution
- Exposure of the portfolio to the Benchmark, Fama–French 3 and 5, momentum, and Carhart factors
- Rolling factor betas and the latest valid input rows

The dashboard runs on `127.0.0.1`. Uploaded CSV data is sent to that local Python server for analysis. Factor datasets are fetched separately from Kenneth French's Data Library usind pandas-datareader.

## Project files

| Path | Purpose |
| --- | --- |
| `main.py` | Analysis of portfolio returns: CSV loading, performance metrics, factor retrieval, and regressions |
| `dashboard_server.py` | Local HTTP server and JSON report |
| `dashboard/` | HTML, CSS, JavaScript, and dashboard-specific notes |
| `returns.csv` | Built-in sample dataset |

To run the command-line analysis instead of the dashboard, run `main.py` from the project directory. Its command-line block reads `returns.csv` and uses a 30-day rolling window.

## Note on the use of AI

The project author wrote the financial analysis in `main.py` following guidance from other projects. The dashboard server and browser interface were developed with AI assistance and subsequently reviewed and edited by the author.
