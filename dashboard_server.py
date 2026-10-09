"""Local dashboard for main.py. Run: python dashboard_server.py"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import main as analyzer


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "dashboard"
MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000


def finite(value):
    """Convert NumPy numbers to JSON numbers and non-finite values to null."""
    number = float(value)
    return number if math.isfinite(number) else None


def series_payload(series):
    return {
        "dates": [date.strftime("%Y-%m-%d") for date in series.index],
        "values": [finite(value) for value in series],
    }


def frame_payload(frame):
    return {
        "dates": [date.strftime("%Y-%m-%d") for date in frame.index],
        "series": {
            column: [finite(value) for value in frame[column]]
            for column in frame.columns
        },
    }


def regression_payload(regression):
    return {
        "label": regression.label,
        "r_squared": finite(regression.r_squared),
        "adj_r_squared": finite(regression.adj_r_squared),
        "observations": regression.observations,
        "alpha_annualized": finite(regression.alpha_annualized),
        "loadings": [
            {
                "name": loading.name,
                "coef": finite(loading.coef),
                "tstat": finite(loading.tstat),
                "pvalue": finite(loading.pvalue),
                "significant": bool(loading.significant),
            }
            for loading in regression.loadings
        ],
    }


def build_report(csv_bytes: bytes, window: int) -> dict:
    if not 20 <= window <= 252:
        raise ValueError("Rolling window must be between 20 and 252 trading days.")
    if not csv_bytes:
        raise ValueError("Choose a non-empty CSV file.")
    if len(csv_bytes) > MAX_CSV_BYTES:
        raise ValueError("CSV file exceeds the 10 MB limit.")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        returns = analyzer.load_file(csv_bytes)

    if len(returns) > MAX_ROWS:
        raise ValueError(f"CSV has more than {MAX_ROWS:,} valid rows.")
    if len(returns) < max(30, window):
        raise ValueError(
            f"At least {max(30, window)} valid daily rows are needed for this window."
        )

    results = analyzer.analyze_performance(returns, window=window)
    portfolio = returns["portfolio_return"]
    benchmark = returns["benchmark_return"]

    return {
        "overview": {
            "start": returns.index.min().strftime("%Y-%m-%d"),
            "end": returns.index.max().strftime("%Y-%m-%d"),
            "observations": len(returns),
            "window": window,
            "factor_source": results.factor_source,
            "warnings": [str(item.message) for item in caught],
        },
        "metrics": {
            "portfolio": {
                key: finite(value)
                for key, value in results.portfolio_performance.to_dict().items()
            },
            "benchmark": {
                key: finite(value)
                for key, value in results.benchmark_performance.to_dict().items()
            },
        },
        "regressions": {
            "capm": regression_payload(results.capm_regression),
            "ff3": regression_payload(results.ff3_regression),
            "ff5": regression_payload(results.ff5_regression),
            "momentum": regression_payload(results.momentum_regression),
            "carhart": regression_payload(results.carhart_regression),
        },
        "charts": {
            "wealth": {
                "dates": series_payload(portfolio)["dates"],
                "series": {
                    "Portfolio": series_payload(analyzer.wealth_index(portfolio))["values"],
                    "Benchmark": series_payload(analyzer.wealth_index(benchmark))["values"],
                },
            },
            "drawdown": {
                "dates": series_payload(portfolio)["dates"],
                "series": {
                    "Portfolio": series_payload(analyzer.drawdowns(portfolio))["values"],
                    "Benchmark": series_payload(analyzer.drawdowns(benchmark))["values"],
                },
            },
            "rolling_sharpe": series_payload(results.rolling_sharpe),
            "rolling_betas": {
                "ff3": frame_payload(results.rolling_betas_ff3),
                "ff5": frame_payload(results.rolling_betas_ff5),
                "momentum": frame_payload(results.rolling_betas_mom),
                "carhart": frame_payload(results.rolling_betas_carhart),
            },
            "daily_returns": {
                "portfolio": [finite(value) for value in portfolio],
                "benchmark": [finite(value) for value in benchmark],
            },
        },
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def send_bytes(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        assets = {
            "/": (ASSETS / "index.html", "text/html; charset=utf-8"),
            "/app.css": (ASSETS / "app.css", "text/css; charset=utf-8"),
            "/app.js": (ASSETS / "app.js", "text/javascript; charset=utf-8"),
            "/sample.csv": (ROOT / "returns.csv", "text/csv; charset=utf-8"),
        }
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
        elif path in assets:
            filename, content_type = assets[path]
            self.send_bytes(200, filename.read_bytes(), content_type)
        else:
            self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        request = urlsplit(self.path)
        if request.path != "/api/analyze":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_CSV_BYTES:
                raise ValueError("Choose a CSV file smaller than 10 MB.")
            window = int(parse_qs(request.query).get("window", ["60"])[0])
            report = build_report(self.rfile.read(length), window)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (RuntimeError, KeyError) as exc:
            self.send_json(502, {"error": f"Analysis could not complete: {exc}"})
        except Exception:
            self.log_exception()
            self.send_json(500, {"error": "Unexpected analysis error. Check the server terminal."})
        else:
            self.send_json(200, report)

    def log_exception(self):
        import traceback

        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Local performance analysis dashboard")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Dashboard ready at http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
