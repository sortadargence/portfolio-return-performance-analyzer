import io
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

TRADING_DAYS = 252

def _normalize(name: str) -> str:   
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")

def load_file(file_path) -> pd.DataFrame:

    if isinstance(file_path, bytes):
        file_path = io.BytesIO(file_path)
    elif isinstance(file_path, str) and ("\n" in file_path or "," in file_path):
        file_path = io.StringIO(file_path)

    df = pd.read_csv(file_path)
    if df.empty:
        raise ValueError("The provided CSV file is empty.")

    lookup_columns = [_normalize(col) for col in df.columns]

    def find_column(name: str) -> str:
        matches = [
            original for original, normalized in zip(df.columns, lookup_columns)
            if name in normalized and (name != "return" or "benchmark" not in normalized)
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {name!r} column, found {matches}.")
        return matches[0]

    date_column = find_column("date")
    return_column = find_column("return")
    benchmark_column = find_column("benchmark")

    out = pd.DataFrame(
        {
            "portfolio_return": pd.to_numeric(df[return_column], errors="coerce"),
            "benchmark_return": pd.to_numeric(df[benchmark_column], errors="coerce"),
        }
    )
    out.index = pd.to_datetime(df[date_column], errors="coerce")
    out.index.name = "date"

    out = out.loc[out.index.notna()].dropna().sort_index()
    if out.empty:
        raise ValueError("The CSV contains no valid dated return rows.")
    if out.index.has_duplicates:
        raise ValueError("The CSV contains duplicate dates.")

    if out[["portfolio_return", "benchmark_return"]].abs().median().median() > 1:
        warnings.warn(
            "The returns provided appear to be in percentage format (e.g., 5 for 5%). "
            "Please ensure that the returns are in decimal format."
        )

    return out


def wealth_index(returns: pd.Series, initial_value: float = 1.0) -> pd.Series:

    return initial_value * (1 + returns).cumprod()


def drawdowns(returns: pd.Series) -> pd.Series:
    wealth = wealth_index(returns)
    current_max = wealth.cummax()

    return (wealth - current_max) / current_max


def max_drawdown(returns: pd.Series) -> float:
    return float(drawdowns(returns).min())


def annualized_return(returns: pd.Series) -> float:
    n = len(returns)
    if n == 0:
        raise ValueError("The returns series is empty.")
    total_growth = float((1 + returns).prod())
    if total_growth <= 0:
        raise ValueError("Total growth is non-positive, cannot compute annualized return.")
    
    return total_growth ** (TRADING_DAYS / n) - 1


def annualized_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, risk_free_rate: float | pd.Series = 0.0) -> float:
    excess_returns = returns - risk_free_rate
    volatility = excess_returns.std(ddof=1)
    if volatility == 0:
        raise ValueError("Volatility is zero, cannot compute Sharpe ratio.")
    
    return float(excess_returns.mean() / volatility * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_rate: float | pd.Series = 0.0) -> float:
    excess_returns = returns - risk_free_rate
    downside_returns = excess_returns.clip(upper=0)
    downside_deviation = float(np.sqrt(downside_returns.pow(2).mean()))
    if downside_deviation == 0:
        raise ValueError("Downside deviation is zero, cannot compute Sortino ratio.")
    
    return float(excess_returns.mean() / downside_deviation * np.sqrt(TRADING_DAYS))


def rolling_sharpe_ratio(returns: pd.Series, window: int = 30, risk_free_rate: float | pd.Series = 0.0) -> pd.Series:
    excess_returns = returns - risk_free_rate
    mean = excess_returns.rolling(window = window).mean()
    std = excess_returns.rolling(window = window).std(ddof=1)

    return mean / std * np.sqrt(TRADING_DAYS)

@dataclass
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float

    def to_dict(self) -> dict:
        return {
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "annualized_volatility": self.annualized_volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
        }


def performance_metrics(returns: pd.Series, risk_free_rate: float | pd.Series = 0.0) -> PerformanceMetrics:
    return PerformanceMetrics(
        total_return = float((1 + returns).prod() -1),
        annualized_return = annualized_return(returns),
        annualized_volatility = annualized_volatility(returns),
        sharpe_ratio = sharpe_ratio(returns, risk_free_rate),
        sortino_ratio = sortino_ratio(returns, risk_free_rate),
        max_drawdown = max_drawdown(returns)
    )


@dataclass
class FactorLoading:
    name: str
    coef: float
    tstat: float
    pvalue: float
    annualized: Optional[float] = None

    @property
    def significant(self) -> bool:
        return self.pvalue < 0.05


@dataclass
class RegressionResults:
    label: str
    loadings: list[FactorLoading]
    r_squared: float
    adj_r_squared: float
    observations: int
    alpha_annualized: float 

    def loading(self, name: str) -> Optional[FactorLoading]:
        for loading in self.loadings:
            if loading.name.lower() == name.lower():
                return loading
        return None


def _ols(y: pd.Series, X: pd.DataFrame, label: str) -> RegressionResults:
    X = sm.add_constant(X, has_constant = "add")
    model = sm.OLS(y, X, missing = "drop").fit()

    loadings: list[FactorLoading] = []
    for name in X.columns:
        coef = float(model.params[name])
        annualized = coef * TRADING_DAYS if name == "const" else None
        loadings.append(
            FactorLoading(
                name = "Alpha" if name == "const" else name,
                coef = coef,
                tstat = float(model.tvalues[name]),
                pvalue = float(model.pvalues[name]),
                annualized = annualized
            )
        )

    alpha_annualized = float(model.params["const"] * TRADING_DAYS)
    
    return RegressionResults(
        label = label,
        loadings = loadings,
        r_squared = float(model.rsquared),
        adj_r_squared = float(model.rsquared_adj),
        observations = int(model.nobs),
        alpha_annualized = alpha_annualized
    )


def benchmark_regression(returns: pd.Series, bechmark_returns: pd.Series, risk_free_rate: float | pd.Series = 0.0) -> RegressionResults:
    y = (returns - risk_free_rate).rename("excess_return")
    X = (bechmark_returns - risk_free_rate).rename("excess_benchmark")
    data = pd.concat([y, X], axis = 1).dropna()
    result = _ols(data["excess_return"], data[["excess_benchmark"]],label = "Benchmark Regression")
    for loading in result.loadings:
        if loading.name == "excess_benchmark":
            loading.name = "Beta"

    return result


FF3 = "FF3"
FF5 = "FF5"
CARHART = "Carhart"
MOMENTUM = "Momentum"

FF3_FACTORS = ["Mkt-RF", "SMB", "HML"]
FF5_FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
CARHART_FACTORS = ["Mkt-RF", "SMB", "HML", "MOM"]
MOMENTUM_FACTOR = ["MOM"]


@dataclass
class FactorData:
    factors: pd.DataFrame
    source: str


def _scale_factors(factors: pd.DataFrame) -> pd.DataFrame:
    return factors / 100.0




def get_factors(start_date, end_date, factor_model: str = FF5) -> FactorData:
    from pandas_datareader.famafrench import FamaFrenchReader

    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)
    if pd.isna(start_date) or pd.isna(end_date) or start_date > end_date:
        raise ValueError("A valid start_date must be earlier than or equal to end_date.")

    datasets = {
        FF3: "F-F_Research_Data_Factors_daily",
        FF5: "F-F_Research_Data_5_Factors_2x3_daily",
        MOMENTUM: "F-F_Momentum_Factor_daily",
    }
    valid_models = set(datasets) | {CARHART}
    if not isinstance(factor_model, str) or factor_model not in valid_models:
        raise ValueError(f"Invalid factor_model. Must be one of {sorted(valid_models)}.")

    def fetch(dataset: str) -> pd.DataFrame:
        data = FamaFrenchReader(dataset, start=start_date, end=end_date).read()[0]
        data.index = pd.to_datetime(data.index.astype(str))
        data.columns = [str(column).strip() for column in data.columns]
        data = data.rename(columns={column: "MOM" for column in data.columns if column.casefold() == "mom"})
        return data

    try:
        if factor_model == CARHART:
            ff3 = fetch(datasets[FF3])
            momentum = fetch(datasets[MOMENTUM])
            factors = ff3.join(momentum[["MOM"]], how="inner")
        elif factor_model == MOMENTUM:
            momentum = fetch(datasets[MOMENTUM])
            ff3 = fetch(datasets[FF3])
            factors = momentum[["MOM"]].join(ff3[["RF"]], how="inner")
        else:
            factors = fetch(datasets[factor_model])
    except Exception as e:
        raise RuntimeError(f"Failed to fetch factor data: {e}") from e

    if factors.empty:
        raise ValueError("No factor data available for the specified date range.")

    return FactorData(
        factors=_scale_factors(factors),
        source="pandas_datareader (Kenneth French's Data Library)",
    )


def factor_regression(portfolio: pd.Series, factor_data: FactorData, factors: list[str]) -> RegressionResults:
    df = factor_data.factors
    merged = pd.concat([portfolio.rename("portfolio_return"), df], axis = 1, join = "inner").dropna()
    if len(merged) == 0:
        raise ValueError("No overlapping data between portfolio returns and factor data.")
    excess_portfolio = merged["portfolio_return"] - merged["RF"]
    if len(factors) == 1:
        label = f"Momentum Factor Regression"
    elif len(factors) == 4:
        label = f"Carhart 4-Factor Regression"
    else:
        label = f"Fama-French {len(factors)}-Factor Regression"
    return _ols(excess_portfolio, merged[factors], label = label)


def rolling_factor__betas(portfolio: pd.Series, factor_data: FactorData, factors: list[str], window: int = 30) -> pd.DataFrame:
    df = factor_data.factors
    merged = pd.concat([portfolio.rename("portfolio_return"), df], axis = 1, join = "inner").dropna()
    excess_portfolio = merged["portfolio_return"] - merged["RF"]
    X = sm.add_constant(merged[factors], has_constant = "add")

    idx = merged.index
    records = []
    for i in range(window, len(merged) + 1):
        sl = slice (i - window, i)
        y_win = excess_portfolio.iloc[sl]
        X_win = X.iloc[sl]
        try:
            betas = sm.OLS(y_win, X_win, missing = "drop").fit().params
        except Exception as e:
            raise RuntimeError(f"Failed to compute rolling betas for window ending at index {i}: {e}")

        row = {f: float(betas.get(f, np.nan)) for f in factors}
        records.append((idx[i - 1], row))

    if not records:
        return pd.DataFrame(columns = factors)
    out = pd.DataFrame([r for _, r in records], index = [d for d, _ in records])
    out.index.name = "date"
    return out



@dataclass
class AnalysisResults:
    returns: pd.DataFrame
    risk_free_rate: pd.Series
    portfolio_performance: PerformanceMetrics
    benchmark_performance: PerformanceMetrics
    capm_regression: RegressionResults
    ff3_regression: RegressionResults
    ff5_regression: RegressionResults
    momentum_regression: RegressionResults
    carhart_regression: RegressionResults
    rolling_betas_ff3: pd.DataFrame
    rolling_betas_ff5: pd.DataFrame
    rolling_betas_mom: pd.DataFrame
    rolling_betas_carhart: pd.DataFrame
    rolling_sharpe: pd.Series
    factor_source: str
    window: int


def analyze_performance(returns: pd.DataFrame, window: int = 30) -> AnalysisResults:
    portfolio_returns = returns["portfolio_return"]
    benchmark_returns = returns["benchmark_return"]
    start_date, end_date = returns.index.min(), returns.index.max()

    ff5_data = get_factors(start_date, end_date, factor_model=FF5)
    carhart_data = get_factors(start_date, end_date, factor_model=CARHART)
    risk_free_rate = ff5_data.factors["RF"].reindex(returns.index).ffill()
    if risk_free_rate.isna().any():
        raise ValueError("Risk-free rate data does not cover all return dates.")

    portfolio_performance = performance_metrics(portfolio_returns, risk_free_rate)
    benchmark_performance = performance_metrics(benchmark_returns, risk_free_rate)
    capm_regression = benchmark_regression(portfolio_returns, benchmark_returns, risk_free_rate)
    ff3_regression = factor_regression(portfolio_returns, carhart_data, FF3_FACTORS)
    ff5_regression = factor_regression(portfolio_returns, ff5_data, FF5_FACTORS)
    momentum_regression = factor_regression(portfolio_returns, carhart_data, MOMENTUM_FACTOR)
    carhart_regression = factor_regression(portfolio_returns, carhart_data, CARHART_FACTORS)
    rolling_betas_ff3 = rolling_factor__betas(portfolio_returns, carhart_data, FF3_FACTORS, window=window)
    rolling_betas_ff5 = rolling_factor__betas(portfolio_returns, ff5_data, FF5_FACTORS, window=window)
    rolling_betas_mom = rolling_factor__betas(portfolio_returns, carhart_data, MOMENTUM_FACTOR, window=window)
    rolling_betas_carhart = rolling_factor__betas(portfolio_returns, carhart_data, CARHART_FACTORS, window=window)
    rolling_sharpe = rolling_sharpe_ratio(portfolio_returns, window=window, risk_free_rate=risk_free_rate)

    return AnalysisResults(
        returns=returns,
        risk_free_rate=risk_free_rate,
        portfolio_performance=portfolio_performance,
        benchmark_performance=benchmark_performance,
        capm_regression=capm_regression,
        ff3_regression=ff3_regression,
        ff5_regression=ff5_regression,
        momentum_regression=momentum_regression,
        carhart_regression=carhart_regression,
        rolling_betas_ff3=rolling_betas_ff3,
        rolling_betas_ff5=rolling_betas_ff5,
        rolling_betas_mom=rolling_betas_mom,
        rolling_betas_carhart=rolling_betas_carhart,
        rolling_sharpe=rolling_sharpe,
        factor_source=ff5_data.source,
        window=window,
    )


if __name__ == "__main__":

    csv_path = "returns.csv"
    returns = load_file(csv_path)
    results = analyze_performance(returns, window = 30)

    print(f"Loaded {len(returns)} rows of returns data.")
    print(f"Analyzed performance for {len(results.returns)} time periods.")
    print("\nPortfolio Performance Metrics:")
    for key, value in results.portfolio_performance.to_dict().items():
        print(f"{key}: {value:.4f}")
    print("\nBenchmark Performance Metrics:")
    for key, value in results.benchmark_performance.to_dict().items():
        print(f"{key}: {value:.4f}")
    beta = results.capm_regression.loading("Beta")
    print("annualized alpha:", results.capm_regression.alpha_annualized)
    print("beta:", beta)
    print("r-squared:", results.capm_regression.r_squared)
    print("Fama-French factor loadings:")
    for loading in results.ff5_regression.loadings:
        print(f"{loading.name}: {loading.coef:.4f}")
    print("Rolling betas shape:", results.rolling_betas_ff5.shape)

    
