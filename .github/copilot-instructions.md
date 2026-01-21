# Kalshi AI Trading Bot - AI Agent Instructions

## Architecture Overview

This is a multi-strategy, AI-powered automated trading system for Kalshi prediction markets. The system uses **xAI's Grok-4** as the primary AI model for market analysis and decision-making.

### Core Components

**Multi-Agent Decision Pipeline** ([src/jobs/](../src/jobs/))
- `ingest.py` - Fetches markets from Kalshi API, filters by volume/expiry
- `decide.py` - Multi-agent AI analysis (Forecaster → Critic → Trader) with cost controls
- `execute.py` - Order placement via Kalshi API (market/limit orders)
- `track.py` - Position monitoring with dynamic exit strategies (stop-loss, take-profit, time-based)
- `evaluate.py` - Performance analytics and portfolio rebalancing

**Trading Strategies** ([src/strategies/](../src/strategies/))
- `unified_trading_system.py` - Orchestrates all strategies with capital allocation (30% market making, 40% directional, 30% quick flip)
- `market_making.py` - Spread trading and liquidity provision
- `portfolio_optimization.py` - Kelly Criterion position sizing and risk parity allocation
- `quick_flip_scalping.py` - Short-term momentum trading with rapid exits

**Infrastructure**
- `src/clients/kalshi_client.py` - Kalshi API wrapper with HMAC signing authentication
- `src/clients/xai_client.py` - xAI Grok integration with JSON repair and usage tracking
- `src/utils/database.py` - SQLite async database with 1379 lines managing markets, positions, orders, trade logs, LLM queries, performance snapshots
- `src/config/settings.py` - Centralized configuration with dual environment support (PROD vs DEMO)

### Data Flow

```
Markets (Kalshi) → Ingest → Filter → Decide (AI) → Execute → Track → Evaluate
                                         ↓
                                  Database (SQLite)
                                         ↓
                              Dashboard (Streamlit)
```

## 🚨 AI Agent Guidelines

### Documentation Practices

**DO NOT create unnecessary markdown files.** When making changes or analyzing the system:
- ❌ Do NOT create summary files like `CHANGES.md`, `ANALYSIS.md`, `SUMMARY.md` unless explicitly requested
- ❌ Do NOT create documentation for every small change or analysis
- ✅ Make changes directly to code and existing documentation
- ✅ Provide concise summaries in responses, not separate files
- ✅ Update relevant existing documentation (README.md, etc.) only when necessary

### Production Log Analysis

**The bot runs in production on remote host `adrastea`.** When asked to analyze logs or performance:

1. **First, pull logs from production:**
   ```bash
   ssh adrastea "/usr/local/bin/docker logs kalshi-trading-bot --tail 500" > /tmp/production_logs.txt
   ```

2. **Copy database for analysis (optional):**
   ```bash
   ssh adrastea "/usr/local/bin/docker cp kalshi-trading-bot:/app/data/trading_system.db /tmp/trading_system.db" && \
     scp adrastea:/tmp/trading_system.db /tmp/production_db.db
   ```

3. **Use available inspection scripts to analyze the database:**
   - `inspect_prod_db.py` - Verify positions table integrity and check for duplicates
   - `inspect_activity.py` - Review recent analyses and trade logs
   - `extract_grok_analysis.py` - Extract and review AI reasoning from logs

4. **Then analyze the pulled logs/data locally** - don't analyze stale local logs

**Container details:**
- Host: `adrastea` (accessible via SSH)
- Container name: `kalshi-trading-bot`
- Log location: Docker container logs
- Database: `/app/data/trading_system.db` (inside container)
- Dashboard: Exposed on port 8501

**Quick commands:**
```bash
# View live logs
ssh adrastea "/usr/local/bin/docker logs -f kalshi-trading-bot"

# Check container status
ssh adrastea "/usr/local/bin/docker ps | grep kalshi-trading-bot"

# View recent errors
ssh adrastea "/usr/local/bin/docker logs kalshi-trading-bot --tail 100 | grep ERROR"

# Copy latest database
ssh adrastea "/usr/local/bin/docker cp kalshi-trading-bot:/app/data/trading_system.db /tmp/trading_system.db" && \
  scp adrastea:/tmp/trading_system.db /tmp/production_db.db
```

## Critical Patterns & Conventions

### 1. Environment Configuration (PROD vs DEMO)

**CRITICAL**: The system supports dual environments with separate credentials:
- DEMO (default): `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY`, `https://demo-api.kalshi.co`
- PROD (live trading): `KALSHI_API_KEY_PROD`, `KALSHI_PRIVATE_KEY_PROD`, `https://api.elections.kalshi.com`

Switch environments via `settings.api.configure_environment(use_live=True/False)`. See [settings.py:30-42](../src/config/settings.py#L30-L42).

### 2. AI Model Configuration

**DO NOT CHANGE**: `primary_model: str = "grok-4"` ([settings.py:65](../src/config/settings.py#L65))  
The system is optimized for Grok-4's reasoning capabilities. Changing this breaks prompt engineering and cost calculations.

### 3. Cost Controls & Budget Management

AI analysis has multiple safeguards ([decide.py:62-98](../src/jobs/decide.py#L62-L98)):
- Daily budget limit: Check `get_daily_ai_cost()` before analysis
- Analysis cooldown: Skip markets analyzed within N hours
- Per-market limits: Max analyses per day per market
- Volume thresholds: Don't waste AI calls on low-volume markets

### 4. Database Patterns

**Always initialize database first**: `await db_manager.initialize()` before any operations ([beast_mode_bot.py:102](../beast_mode_bot.py#L102))

**Use dataclass models** ([database.py:12-127](../src/utils/database.py#L12-L127)):
- `Market` - Market data snapshots
- `Position` - Active trading positions with exit strategies
- `Order` - Order lifecycle tracking (pending → placed → filled)
- `TradeLog` - Closed trades with P&L attribution
- `BalanceSnapshot` - Portfolio value over time

**LLM query logging**: All AI calls are logged with `log_llm_query(prompt, response, cost, strategy)` for dashboard review and cost tracking.

### 5. Multi-Agent AI Prompting

The system uses a **Forecaster → Critic → Trader** pattern ([prompts.py:5-63](../src/utils/prompts.py#L5-L63)):

```python
MULTI_AGENT_PROMPT_TPL = """
1. **Forecaster** – Estimate true YES probability
2. **Critic** – Challenge assumptions and biases
3. **Trader** – Final decision with JSON output
"""
```

**JSON repair**: AI responses are cleaned with `json_repair.repair_json()` ([xai_client.py](../src/clients/xai_client.py)) since Grok sometimes adds commentary outside JSON blocks.

### 6. Position Sizing & Risk Management

**Primary method**: Kelly Criterion ([settings.py:77-80](../src/config/settings.py#L77-L80))
- `kelly_fraction = 0.75` (aggressive multiplier)
- `max_single_position = 0.05` (5% portfolio cap)

**Legacy fallback**: Fixed percentage with confidence multiplier ([decide.py:18-55](../src/jobs/decide.py#L18-L55))

**Exit strategies**: Positions include `stop_loss_price`, `take_profit_price`, `max_hold_hours`, `target_confidence_change` ([database.py:34-42](../src/utils/database.py#L34-L42)).

## Developer Workflows

### Running the Bot

```bash
# Paper trading (DEMO environment)
python beast_mode_bot.py

# Live trading (PROD environment) - prompts for confirmation
python beast_mode_bot.py --live

# With dashboard
python beast_mode_bot.py --dashboard
```

### Testing

**NEVER run `pytest` directly** - it's slow with many API calls.  
Use the interactive test runner:

```bash
python run_tests.py
```

Options:
1. Quick tests (30s) - imports, config, database only
2. Full tests (2-3 min) - includes API calls
3. Custom pattern - specify test filter

For CI/testing patterns, see [run_tests.py](../run_tests.py) and [COMMANDS_REFERENCE.md](../COMMANDS_REFERENCE.md).

### Database Schema Changes

**Schema is code-first**: Modify dataclasses in [database.py](../src/utils/database.py#L12-L127), then run:

```bash
python fix_database_schema.py  # Handles migrations without data loss
```

Never manually ALTER TABLE - use the migration script.

### Monitoring

**Streamlit Dashboard** ([trading_dashboard.py](../trading_dashboard.py), [beast_mode_dashboard.py](../beast_mode_dashboard.py)):

```bash
python launch_dashboard.py
```

Shows:
- Real-time P&L and positions
- Strategy performance comparison
- **LLM query review** - every Grok prompt/response logged with cost attribution
- Risk alerts and system health

See [README_DASHBOARD.md](../README_DASHBOARD.md) for dashboard features.

## Integration Points

### Kalshi API ([kalshi_client.py](../src/clients/kalshi_client.py))

**Authentication**: Uses private key + HMAC signing, NOT Bearer tokens.  
Key files: `kalshi_private_key.pem` (demo), `kalshi_private_key.prod.pem` (live).

**Rate limiting**: Exponential backoff with max 5 retries ([kalshi_client.py:44-46](../src/clients/kalshi_client.py#L44-L46)).

**Order placement**: Requires `yes_price` or `no_price` even for market orders ([execute.py:57-66](../src/jobs/execute.py#L57-L66)).

### xAI Grok API ([xai_client.py](../src/clients/xai_client.py))

**SDK**: Uses `xai_sdk.AsyncClient`, not OpenAI client ([xai_client.py:18-20](../src/clients/xai_client.py#L18-L20)).

**Model names**: `grok-4`, `grok-3` (fallback) - not `grok-beta` or older naming.

**Token limits**: `ai_max_tokens = 8000` optimized for Grok-4 reasoning ([settings.py:68](../src/config/settings.py#L68)).

**Usage tracking**: `DailyUsageTracker` enforces budget limits with automatic exhaustion detection ([xai_client.py:29-35](../src/clients/xai_client.py#L29-L35)).

## Project-Specific Quirks

### 1. "Beast Mode" Terminology

"Beast Mode" = unified multi-strategy system with no time restrictions and aggressive capital deployment. Not a separate mode - it's the main production system ([beast_mode_bot.py](../beast_mode_bot.py)).

### 2. Strategy Attribution

Every position/trade tracks `strategy` field: `"market_making"`, `"directional_trading"`, `"quick_flip_scalping"`. Used for dashboard performance breakdown.

### 3. Async Everywhere

**All** database operations, API calls, and job functions are `async`. Never use blocking I/O. Main entry points use `asyncio.run()` ([beast_mode_bot.py](../beast_mode_bot.py)).

### 4. Logging Pattern

Use `TradingLoggerMixin` base class ([logging_setup.py](../src/utils/logging_setup.py)) for structured logging:

```python
self.logger.info("Message", key=value, another_key=value)  # Structured
self.logger.warning("Issue", error=str(e))
```

### 5. Confidence Thresholds

Multiple confidence thresholds coexist:
- `min_confidence_to_trade = 0.50` - general trading ([settings.py:61](../src/config/settings.py#L61))
- `min_confidence_threshold = 0.45` - AI analysis trigger ([settings.py:94](../src/config/settings.py#L94))
- `high_confidence_threshold = 0.95` - special high-confidence strategy ([settings.py:90](../src/config/settings.py#L90))

Context matters - check which threshold applies to your code path.

## Common Tasks

### Adding a New Strategy

1. Create strategy file in `src/strategies/`
2. Implement `async def run_<strategy>_strategy()` function
3. Add to `unified_trading_system.py` orchestration
4. Update `TradingSystemConfig` capital allocation
5. Add strategy name to database `strategy` field enum

### Modifying AI Prompts

Edit `src/utils/prompts.py` templates. Test changes thoroughly - prompt engineering directly impacts trading decisions. Consider A/B testing with confidence scoring.

### Adding New Market Filters

Update `run_ingestion()` in [ingest.py](../src/jobs/ingest.py) with new filter criteria. Common filters: `volume`, `expiration_ts`, `category`, `status`. Always log filter reasons for debugging.

### Performance Analysis

Query database directly or use helper scripts:
- `analyze_performance.py` - Historical P&L analysis
- `view_strategy_performance.py` - Per-strategy breakdown
- `portfolio_health_check.py` - Risk metrics

All use `DatabaseManager` queries - see [database.py:400-1379](../src/utils/database.py#L400-L1379) for available methods.

## References

- Main README: [README.md](../README.md)
- Commands reference: [COMMANDS_REFERENCE.md](../COMMANDS_REFERENCE.md)
- Dashboard guide: [README_DASHBOARD.md](../README_DASHBOARD.md)
- Performance system: [README_PERFORMANCE_SYSTEM.md](../README_PERFORMANCE_SYSTEM.md)
- Quick flip strategy: [README_QUICK_FLIP_STRATEGY.md](../README_QUICK_FLIP_STRATEGY.md)

## Key Files for Context

When working on:
- **Trading logic**: Read [decide.py](../src/jobs/decide.py), [execute.py](../src/jobs/execute.py), [track.py](../src/jobs/track.py)
- **Strategy changes**: Start with [unified_trading_system.py](../src/strategies/unified_trading_system.py)
- **API issues**: Check [kalshi_client.py](../src/clients/kalshi_client.py), [xai_client.py](../src/clients/xai_client.py)
- **Database**: [database.py](../src/utils/database.py) is comprehensive (1379 lines) - search for method names
- **Configuration**: [settings.py](../src/config/settings.py) controls all behavior - check before adding new params
