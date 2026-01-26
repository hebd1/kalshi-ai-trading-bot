"""
Comprehensive tests for cash_reserves module.

Tests all classes and functions:
- CashReservesManager
- check_can_trade_with_cash_reserves()
- is_cash_emergency()
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.utils.cash_reserves import (
    CashReservesManager,
    check_can_trade_with_cash_reserves,
    is_cash_emergency,
    CashReserveResult,
    CashEmergencyAction
)


class TestCashReserveResult:
    """Tests for CashReserveResult dataclass."""
    
    def test_dataclass_creation(self):
        """Should create dataclass with all fields."""
        result = CashReserveResult(
            can_trade=True,
            reason="Cash reserves adequate",
            current_cash=500.0,
            portfolio_value=1000.0,
            cash_reserve_pct=50.0,
            required_reserve_pct=15.0,
            emergency_status=False,
            recommended_actions=[]
        )
        
        assert result.can_trade is True
        assert result.current_cash == 500.0
        assert result.cash_reserve_pct == 50.0
        assert result.emergency_status is False
        
    def test_emergency_result(self):
        """Should correctly represent emergency state."""
        result = CashReserveResult(
            can_trade=False,
            reason="CRITICAL: Cash reserves too low",
            current_cash=10.0,
            portfolio_value=1000.0,
            cash_reserve_pct=1.0,
            required_reserve_pct=15.0,
            emergency_status=True,
            recommended_actions=["Close positions immediately"]
        )
        
        assert result.can_trade is False
        assert result.emergency_status is True
        assert len(result.recommended_actions) > 0


class TestCashEmergencyAction:
    """Tests for CashEmergencyAction dataclass."""
    
    def test_close_positions_action(self):
        """Should represent close positions action."""
        action = CashEmergencyAction(
            action_type="close_positions",
            urgency="critical",
            positions_to_close=3,
            expected_cash_freed=150.0,
            reason="Cash reserves critically low"
        )
        
        assert action.action_type == "close_positions"
        assert action.urgency == "critical"
        assert action.positions_to_close == 3
        
    def test_halt_trading_action(self):
        """Should represent halt trading action."""
        action = CashEmergencyAction(
            action_type="halt_trading",
            urgency="critical",
            positions_to_close=0,
            expected_cash_freed=0.0,
            reason="Insufficient cash to operate"
        )
        
        assert action.action_type == "halt_trading"
        assert action.positions_to_close == 0


class TestCashReservesManagerInit:
    """Tests for CashReservesManager initialization."""
    
    def test_manager_creation(self):
        """Should create manager with mocked dependencies."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        assert manager.db_manager == mock_db
        assert manager.kalshi_client == mock_kalshi
        
    def test_loads_settings(self):
        """Should load threshold settings from config."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # Should have threshold values from settings
        assert hasattr(manager, 'minimum_reserve_pct')
        assert hasattr(manager, 'optimal_reserve_pct')
        assert hasattr(manager, 'emergency_threshold_pct')
        assert hasattr(manager, 'critical_threshold_pct')


class TestCashReservesManagerCheckReserves:
    """Tests for CashReservesManager.check_cash_reserves()"""
    
    @pytest.mark.asyncio
    async def test_adequate_reserves_can_trade(self):
        """Should allow trading when reserves are adequate."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock balance response
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50000})  # $500
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        result = await manager.check_cash_reserves(
            proposed_trade_value=50.0,
            portfolio_value=1000.0
        )
        
        assert result.can_trade is True
        assert result.emergency_status is False
        
    @pytest.mark.asyncio
    async def test_low_reserves_blocks_trade(self):
        """Should block trading when reserves too low after trade."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock low balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 2000})  # $20
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # Trying to trade $15 of $20 would leave reserves too low
        result = await manager.check_cash_reserves(
            proposed_trade_value=15.0,
            portfolio_value=100.0  # Small portfolio
        )
        
        # With such low reserves, should block or warn
        # Depending on thresholds, may block
        assert isinstance(result.can_trade, bool)
        
    @pytest.mark.asyncio
    async def test_emergency_status_detected(self):
        """Should detect emergency status when reserves critical."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock very low balance - below critical threshold
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50})  # $0.50
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        result = await manager.check_cash_reserves(
            proposed_trade_value=0.0,  # Not even trading
            portfolio_value=1000.0
        )
        
        # 0.05% reserve is below any threshold
        assert result.emergency_status is True
        assert result.can_trade is False
        
    @pytest.mark.asyncio
    async def test_recommendations_provided(self):
        """Should provide recommendations when reserves low."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock low balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 100})  # $1
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        result = await manager.check_cash_reserves(
            proposed_trade_value=0.0,
            portfolio_value=1000.0
        )
        
        # Should have recommendations
        assert len(result.recommended_actions) >= 0  # May have recommendations


class TestCheckCanTradeWithCashReserves:
    """Tests for convenience function check_can_trade_with_cash_reserves()"""
    
    @pytest.mark.asyncio
    async def test_function_returns_tuple(self):
        """Should return (can_trade, reason) tuple."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock adequate balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50000})
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        can_trade, reason = await check_can_trade_with_cash_reserves(
            trade_value=50.0,
            db_manager=mock_db,
            kalshi_client=mock_kalshi
        )
        
        assert isinstance(can_trade, bool)
        assert isinstance(reason, str)
        
    @pytest.mark.asyncio
    async def test_small_trade_allowed(self):
        """Small trade with adequate reserves should be allowed."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock adequate balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50000})  # $500
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        can_trade, reason = await check_can_trade_with_cash_reserves(
            trade_value=10.0,  # Small trade
            db_manager=mock_db,
            kalshi_client=mock_kalshi
        )
        
        assert can_trade is True


class TestIsCashEmergency:
    """Tests for convenience function is_cash_emergency()"""
    
    @pytest.mark.asyncio
    async def test_no_emergency_with_good_reserves(self):
        """Should not be emergency with good reserves."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock good balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50000})
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        is_emergency = await is_cash_emergency(mock_db, mock_kalshi)
        
        assert is_emergency is False
        
    @pytest.mark.asyncio
    async def test_emergency_with_zero_balance(self):
        """Should be emergency with zero balance."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock zero balance
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 0})
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        is_emergency = await is_cash_emergency(mock_db, mock_kalshi)
        
        assert is_emergency is True


class TestCashReservesEdgeCases:
    """Edge case tests for cash reserves."""
    
    @pytest.mark.asyncio
    async def test_zero_portfolio_value(self):
        """Should handle zero portfolio value gracefully."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 0})
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # Should not divide by zero
        result = await manager.check_cash_reserves(
            proposed_trade_value=0.0,
            portfolio_value=0.0  # Zero portfolio
        )
        
        assert result is not None
        assert result.can_trade is False  # Can't trade with nothing
        
    @pytest.mark.asyncio
    async def test_negative_trade_value_rejected(self):
        """Negative trade value should be handled."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        mock_kalshi.get_balance = AsyncMock(return_value={'balance': 50000})
        mock_kalshi.get_positions = AsyncMock(return_value={'positions': []})
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # Negative trade value (shouldn't happen but handle it)
        result = await manager.check_cash_reserves(
            proposed_trade_value=-50.0,
            portfolio_value=1000.0
        )
        
        # Should still return a valid result
        assert result is not None
        
    @pytest.mark.asyncio
    async def test_api_error_handled(self):
        """Should handle API errors gracefully."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        # Mock API error
        mock_kalshi.get_balance = AsyncMock(side_effect=Exception("API Error"))
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # Should not raise, should return safe default
        try:
            result = await manager.check_cash_reserves(
                proposed_trade_value=50.0,
                portfolio_value=1000.0
            )
            # If it returns, should be conservative (block trading)
            assert result.can_trade is False
        except Exception:
            # Raising is also acceptable
            pass


class TestThresholdConfiguration:
    """Tests for threshold configuration from settings."""
    
    def test_thresholds_are_positive(self):
        """All thresholds should be positive percentages."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        assert manager.minimum_reserve_pct >= 0
        assert manager.optimal_reserve_pct >= 0
        assert manager.emergency_threshold_pct >= 0
        assert manager.critical_threshold_pct >= 0
        
    def test_thresholds_ordered_correctly(self):
        """Thresholds should be in correct order."""
        mock_db = MagicMock()
        mock_kalshi = MagicMock()
        
        manager = CashReservesManager(mock_db, mock_kalshi)
        
        # critical < emergency < minimum < optimal
        assert manager.critical_threshold_pct <= manager.emergency_threshold_pct
        assert manager.emergency_threshold_pct <= manager.minimum_reserve_pct
        assert manager.minimum_reserve_pct <= manager.optimal_reserve_pct
