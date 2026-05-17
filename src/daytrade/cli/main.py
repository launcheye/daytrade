"""``trading-bot`` command-line interface.

Commands:

* ``demo``     — run the canonical BTC decision scenario from PLAN.md
* ``paper``    — run a paper-trading session on deterministic mock data
* ``backtest`` — run a backtest with realistic execution and report metrics
* ``train``    — train the ML model and walk-forward validate it
* ``simulate`` — full end-to-end pipeline: train -> backtest -> reports
* ``config``   — show (and validate) the active configuration

Everything runs offline against a deterministic mock exchange by default.
No command can place a real trade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .. import __version__
from ..backtest import Backtester
from ..config import ConfigError, load_config
from ..demo import (
    DEMO_MACRO_SCENARIO,
    DEMO_REFERENCE_PRICE,
    build_demo_candles,
    build_demo_orderbook,
)
from ..exchanges import generate_random_walk
from ..ml import PredictiveModel, build_dataset
from ..models import ModelKind
from ..pipeline import AnalysisPipeline
from ..reporting import (
    backtest_report_dict,
    backtest_report_markdown,
    decision_report_dict,
    decision_report_markdown,
    render_backtest,
    render_decision,
    render_walkforward,
    save_json,
    save_text,
)
from ..runtime import apply_runtime, get_logger
from ..validation import walk_forward_validate

app = typer.Typer(
    add_completion=False,
    help="daytrade — educational trading research & paper-trading platform. "
         "Cannot place real trades.",
)
_console = Console()
_log = get_logger("cli")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPORTS = _REPO_ROOT / "reports"
_MODELS = _REPO_ROOT / "artifacts"


def _setup(profile: Optional[str]):
    """Load config and apply runtime (logging + deterministic seeding)."""
    try:
        config = load_config(profile)
    except ConfigError as exc:
        _console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    apply_runtime(config.runtime.log_level, config.runtime.deterministic,
                  config.runtime.random_seed)
    return config


def _mock_candles(config, n_bars: int, drift: float, volatility: float):
    """Deterministic mock candle series for paper / backtest / training."""
    return generate_random_walk(
        symbol=config.symbol, n_bars=n_bars, start_price=30_000.0,
        drift=drift, volatility=volatility, seed=config.runtime.random_seed,
    )


@app.command()
def version() -> None:
    """Print the daytrade version."""
    _console.print(f"daytrade {__version__}")


@app.command()
def config(profile: Optional[str] = typer.Option(None, help="Config profile.")) -> None:
    """Show and validate the active configuration."""
    cfg = _setup(profile)
    _console.print(f"[bold green]Config OK[/bold green] — profile '{cfg.profile}'")
    table = Table(title="Active configuration", header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    rows = [
        ("symbol", cfg.symbol),
        ("safety.paper_trading", str(cfg.safety.paper_trading)),
        ("safety.live_trading_enabled", str(cfg.safety.live_trading_enabled)),
        ("runtime.allow_network", str(cfg.runtime.allow_network)),
        ("runtime.deterministic", str(cfg.runtime.deterministic)),
        ("macro.source", cfg.macro.source),
        ("ml.model_kind", cfg.ml.model_kind),
        ("fusion.action_threshold", str(cfg.fusion.action_threshold)),
        ("risk.fee_bps", str(cfg.risk.fee_bps)),
        ("risk.max_daily_loss_pct", str(cfg.risk.max_daily_loss_pct)),
        ("paper.starting_cash", str(cfg.paper.starting_cash)),
    ]
    for k, v in rows:
        table.add_row(k, v)
    _console.print(table)


@app.command()
def demo(
    profile: Optional[str] = typer.Option(None, help="Config profile."),
    save: bool = typer.Option(False, help="Write JSON + Markdown reports."),
) -> None:
    """Run the canonical BTC decision demo from PLAN.md."""
    cfg = _setup(profile)
    _console.rule("[bold]daytrade — canonical decision demo")
    candles = build_demo_candles()
    orderbook = build_demo_orderbook()
    pipeline = AnalysisPipeline(cfg)
    result = pipeline.analyze(
        candles, orderbook, reference_price=DEMO_REFERENCE_PRICE,
        macro_scenario=DEMO_MACRO_SCENARIO,
    )
    render_decision(result, _console)
    if save:
        jp = save_json(decision_report_dict(result), _REPORTS / "demo.json")
        mp = save_text(decision_report_markdown(result), _REPORTS / "demo.md")
        _console.print(f"[green]Saved[/green] {jp} and {mp}")


@app.command()
def paper(
    profile: Optional[str] = typer.Option(None, help="Config profile."),
    bars: int = typer.Option(400, help="Number of mock bars to trade."),
) -> None:
    """Run a paper-trading session on deterministic mock data."""
    cfg = _setup(profile)
    _console.rule("[bold]daytrade — paper-trading session")
    candles = _mock_candles(cfg, bars, drift=0.0004, volatility=0.005)
    result = Backtester(cfg).run(candles)
    m = result.metrics
    _console.print(
        f"Paper session over {m.bars} bars — "
        f"[bold]{m.total_trades}[/bold] simulated trades."
    )
    render_backtest(result, _console)
    _console.print(
        f"Final paper equity: [bold]{m.ending_equity:,.2f}[/bold] "
        f"{cfg.paper.base_currency} (started {m.starting_equity:,.2f})"
    )


@app.command()
def backtest(
    profile: Optional[str] = typer.Option(None, help="Config profile."),
    bars: int = typer.Option(600, help="Number of mock bars to backtest."),
    save: bool = typer.Option(False, help="Write JSON + Markdown reports."),
) -> None:
    """Run a backtest with realistic execution and report metrics."""
    cfg = _setup(profile)
    _console.rule("[bold]daytrade — backtest")
    candles = _mock_candles(cfg, bars, drift=0.0003, volatility=0.006)
    result = Backtester(cfg).run(candles)
    render_backtest(result, _console)
    if save:
        jp = save_json(backtest_report_dict(result), _REPORTS / "backtest.json")
        mp = save_text(backtest_report_markdown(result), _REPORTS / "backtest.md")
        _console.print(f"[green]Saved[/green] {jp} and {mp}")


@app.command()
def train(
    profile: Optional[str] = typer.Option(None, help="Config profile."),
    bars: int = typer.Option(1200, help="Number of mock bars for training."),
) -> None:
    """Train the ML model and run walk-forward validation."""
    cfg = _setup(profile)
    _console.rule("[bold]daytrade — ML training & walk-forward validation")
    candles = _mock_candles(cfg, bars, drift=0.0002, volatility=0.006)

    dataset = build_dataset(candles, cfg)
    _console.print(f"Dataset: {len(dataset)} samples, "
                    f"class balance {dataset.class_balance}")
    model = PredictiveModel(ModelKind(cfg.ml.model_kind), cfg.runtime.random_seed)
    train_result = model.fit(dataset)
    _console.print(
        f"In-sample: accuracy {train_result.accuracy:.3f}, "
        f"AUC {train_result.auc:.3f} "
        f"[dim](in-sample numbers are diagnostic only)[/dim]"
    )

    report = walk_forward_validate(candles, cfg)
    render_walkforward(report, _console)

    path = model.save(_MODELS / "model.pkl")
    _console.print(f"[green]Model saved[/green] -> {path}")


@app.command()
def simulate(
    profile: Optional[str] = typer.Option(None, help="Config profile."),
    bars: int = typer.Option(1200, help="Number of mock bars."),
) -> None:
    """Full end-to-end run: train -> walk-forward -> backtest -> reports."""
    cfg = _setup(profile)
    _console.rule("[bold]daytrade — full simulation")
    candles = _mock_candles(cfg, bars, drift=0.0003, volatility=0.006)

    # 1. Train an ML model on the earlier portion of the data.
    split = int(len(candles) * 0.6)
    dataset = build_dataset(candles[:split], cfg)
    model = PredictiveModel(ModelKind(cfg.ml.model_kind), cfg.runtime.random_seed)
    model.fit(dataset)
    _console.print(f"[1/3] Trained {model.version}")

    # 2. Walk-forward validate.
    report = walk_forward_validate(candles[:split], cfg)
    _console.print(f"[2/3] Walk-forward mean test accuracy "
                    f"{report.mean_test_accuracy:.3f}")
    render_walkforward(report, _console)

    # 3. Backtest the remainder with the trained model (out-of-sample).
    result = Backtester(cfg, model).run(candles[split:])
    _console.print("[3/3] Out-of-sample backtest:")
    render_backtest(result, _console)

    save_json(backtest_report_dict(result), _REPORTS / "simulate.json")
    save_text(backtest_report_markdown(result), _REPORTS / "simulate.md")
    _console.print(f"[green]Reports saved[/green] -> {_REPORTS}")


if __name__ == "__main__":  # pragma: no cover
    app()
