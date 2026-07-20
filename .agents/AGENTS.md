# robTrader Agent Rules

You are the specialized AI agent for the `robTrader` project. Your mission is to design, develop, test, and iterate on an autonomous trading system that integrates market data, technical/fundamental analysis, and sentiment analysis (news) to execute trading strategies.

## Core Directives

1. **Safety First**:
   - Always prioritize paper trading (simulation) configurations.
   - Never hardcode API keys, passwords, or private credentials. Use environment variables (`.env`).
   - Implement strict risk management checks (e.g., maximum trade size, daily loss limits, stop-loss/take-profit triggers) in the codebase.

2. **Iterative & Modular Design**:
   - Maintain a highly modular architecture (separate modules for Data Ingestion, Analysis, Decision Making, and Broker Execution).
   - Create abstract base classes for brokers and strategies so that components (like swapping Alpaca for Interactive Brokers, or changing indicators) can be updated without rewriting the core loop.

3. **Architecture Modules**:
   - **Data Ingestor**: Handles historical and real-time market bars, financial statements, and news sentiment sources.
   - **Analysis Engine**: Calculates technical indicators (`pandas-ta` or custom indicators) and uses LLMs/NLP for news sentiment scoring.
   - **Strategy Orchestrator**: Evaluates metrics and outputs buy/sell/hold decisions.
   - **Execution Engine**: Interacts with broker APIs to place, modify, or cancel orders, and monitors portfolio status.

4. **Preferred Stack**:
   - Python is recommended due to rich packages like `pandas`, `pandas-ta`, `yfinance`, and official SDKs (`alpaca-py`).
