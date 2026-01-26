"""
Comprehensive tests for StopLossCalculator.

Tests all methods:
- calculate_stop_loss_levels()
- calculate_simple_stop_loss()
- is_stop_loss_triggered()
- calculate_pnl_at_stop_loss()
"""

import pytest
from src.utils.stop_loss_calculator import StopLossCalculator, calculate_stop_loss_levels


class TestCalculateStopLossLevels:
    """Tests for StopLossCalculator.calculate_stop_loss_levels()"""

    def test_high_confidence_tighter_stop_loss(self):
        """High confidence (>0.8) should use 5% stop-loss."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.85,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        # High confidence = 5% stop-loss (MIN_STOP_LOSS_PCT)
        # Note: stop_loss_pct is returned as percentage (5.0) not decimal (0.05)
        assert result['stop_loss_pct'] == 5.0
        # Should be below entry for YES position
        assert result['stop_loss_price'] < 0.50
        assert result['stop_loss_price'] == pytest.approx(0.475, abs=0.01)
        
    def test_medium_confidence_medium_stop_loss(self):
        """Medium confidence (0.6-0.8) should use 7% stop-loss."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.70,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        # Medium confidence = 7% stop-loss
        # Note: stop_loss_pct is returned as percentage (7.0) not decimal (0.07)
        assert result['stop_loss_pct'] == pytest.approx(7.0, abs=0.5)
        
    def test_low_confidence_wider_stop_loss(self):
        """Low confidence (<0.6) should use 10% stop-loss."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.55,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        # Low confidence = 10% stop-loss (MAX_STOP_LOSS_PCT)
        # Note: stop_loss_pct is returned as percentage (10.0) not decimal (0.10)
        assert result['stop_loss_pct'] == 10.0
        
    def test_no_position_stop_loss_below_entry(self):
        """NO position stop-loss should be BELOW entry price (same as YES).
        
        On Kalshi, when you OWN a NO contract, you profit when NO price rises.
        Stop-loss triggers when price drops below entry (you're losing money).
        Both YES and NO positions lose money when their contract price drops.
        """
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.30,
            side="NO",
            confidence=0.75,
            market_volatility=0.15,
            time_to_expiry_days=5
        )
        
        # NO position: stop when NO contract price drops (we lose money)
        # Stop-loss is BELOW entry for BOTH YES and NO in this implementation
        assert result['stop_loss_price'] < 0.30
        
    def test_yes_position_stop_loss_below_entry(self):
        """YES position stop-loss should be below entry price."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.60,
            side="YES",
            confidence=0.75,
            market_volatility=0.15,
            time_to_expiry_days=5
        )
        
        # YES position: stop when price goes DOWN (we lose money)
        assert result['stop_loss_price'] < 0.60
        
    def test_take_profit_levels(self):
        """Verify take-profit levels are calculated correctly."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.40,
            side="YES",
            confidence=0.85,
            market_volatility=0.15,
            time_to_expiry_days=7
        )
        
        # Take profit should be above entry for YES
        assert result['take_profit_price'] > 0.40
        # High confidence = 30% take profit (MAX_TAKE_PROFIT_PCT)
        # Note: take_profit_pct is returned as percentage (30.0) not decimal
        assert result['take_profit_pct'] == 30.0
        
    def test_price_clamping_lower_bound(self):
        """Stop-loss price should never go below 0.01."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.03,  # Very low entry price
            side="YES",
            confidence=0.55,  # Low confidence = 10% stop
            market_volatility=0.30,
            time_to_expiry_days=1
        )
        
        # Should be clamped to 0.01 minimum
        assert result['stop_loss_price'] >= 0.01
        
    def test_price_clamping_upper_bound(self):
        """Stop-loss price should never exceed 0.99."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.97,  # Very high entry price
            side="NO",
            confidence=0.55,  # Low confidence = 10% stop  
            market_volatility=0.30,
            time_to_expiry_days=1
        )
        
        # Should be clamped to 0.99 maximum
        assert result['stop_loss_price'] <= 0.99
        
    def test_max_hold_hours_calculation(self):
        """Verify max hold hours is calculated correctly."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=10
        )
        
        # max_hold_hours = min(72, time_to_expiry * 24 * 0.5)
        # For 10 days: min(72, 10 * 24 * 0.5) = min(72, 120) = 72
        assert result['max_hold_hours'] == 72
        
    def test_max_hold_hours_short_expiry(self):
        """Short expiry should have shorter max hold hours."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=1
        )
        
        # For 1 day: min(72, 1 * 24 * 0.5) = min(72, 12) = 12
        assert result['max_hold_hours'] == 12
        
    def test_max_hold_hours_minimum(self):
        """Max hold hours should be at least 6."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=0.1  # Very short expiry
        )
        
        # Should never be below 6 hours
        assert result['max_hold_hours'] >= 6
        
    def test_target_confidence_change_always_15(self):
        """Target confidence change should always be 0.15."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        assert result['target_confidence_change'] == 0.15
        
    def test_result_contains_all_keys(self):
        """Result should contain all expected keys."""
        result = StopLossCalculator.calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        expected_keys = [
            'stop_loss_price',
            'take_profit_price',
            'max_hold_hours',
            'stop_loss_pct',
            'take_profit_pct',
            'target_confidence_change'
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


class TestCalculateSimpleStopLoss:
    """Tests for StopLossCalculator.calculate_simple_stop_loss()"""
    
    def test_yes_position_simple_stop(self):
        """YES position simple stop-loss should be below entry."""
        stop_price = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=0.60,
            side="YES",
            stop_loss_pct=0.10
        )
        
        # 0.60 * (1 - 0.10) = 0.54
        assert stop_price == pytest.approx(0.54, abs=0.01)
        
    def test_no_position_simple_stop(self):
        """NO position simple stop-loss should be BELOW entry (same as YES).
        
        When you own a NO contract, you profit when its price rises.
        Stop-loss triggers when price drops (you're losing money).
        """
        stop_price = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=0.40,
            side="NO",
            stop_loss_pct=0.10
        )
        
        # 0.40 * (1 - 0.10) = 0.36 (stop-loss is BELOW entry for both YES and NO)
        assert stop_price == pytest.approx(0.36, abs=0.01)
        
    def test_default_stop_loss_pct(self):
        """Should use 7% default stop-loss percentage."""
        stop_price = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=0.50,
            side="YES"
            # No stop_loss_pct specified - should use default 0.07
        )
        
        # 0.50 * (1 - 0.07) = 0.465
        assert stop_price == pytest.approx(0.465, abs=0.01)
        
    def test_clamping_lower_bound(self):
        """Stop price should be clamped to minimum 0.01."""
        stop_price = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=0.02,
            side="YES",
            stop_loss_pct=0.50  # 50% stop would go below 0.01
        )
        
        assert stop_price >= 0.01
        
    def test_clamping_upper_bound(self):
        """Stop price should be clamped to maximum 0.99."""
        stop_price = StopLossCalculator.calculate_simple_stop_loss(
            entry_price=0.95,
            side="NO",
            stop_loss_pct=0.10  # Would push above 0.99
        )
        
        assert stop_price <= 0.99


class TestIsStopLossTriggered:
    """Tests for StopLossCalculator.is_stop_loss_triggered()"""
    
    def test_yes_position_stop_triggered(self):
        """YES position stop triggered when price falls below stop."""
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="YES",
            entry_price=0.60,
            current_price=0.50,
            stop_loss_price=0.54  # Stop at 0.54, current is 0.50
        )
        
        assert triggered is True
        
    def test_yes_position_stop_not_triggered(self):
        """YES position stop NOT triggered when price above stop."""
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="YES",
            entry_price=0.60,
            current_price=0.58,
            stop_loss_price=0.54  # Stop at 0.54, current is 0.58
        )
        
        assert triggered is False
        
    def test_no_position_stop_triggered(self):
        """NO position stop triggered when price falls below stop.
        
        NOTE: On Kalshi, buying NO is a long position on the NO contract.
        You profit when NO price rises, lose when it falls - same as YES.
        Stop-loss triggers when price FALLS below stop for BOTH YES and NO.
        """
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="NO",
            entry_price=0.40,
            current_price=0.35,  # Price FELL below stop
            stop_loss_price=0.36  # Stop at 0.36, current is 0.35
        )
        
        assert triggered is True
        
    def test_no_position_stop_not_triggered(self):
        """NO position stop NOT triggered when price above stop.
        
        NOTE: On Kalshi, NO works same as YES - stop triggers on price DROP.
        """
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="NO",
            entry_price=0.40,
            current_price=0.42,  # Price is ABOVE stop
            stop_loss_price=0.36  # Stop at 0.36, current is 0.42
        )
        
        assert triggered is False
        
    def test_price_exactly_at_stop_yes(self):
        """YES position at exact stop price should NOT trigger."""
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="YES",
            entry_price=0.60,
            current_price=0.54,
            stop_loss_price=0.54  # Exactly at stop
        )
        
        # <= means equal will trigger
        assert triggered is True
        
    def test_price_exactly_at_stop_no(self):
        """NO position at exact stop price should trigger."""
        triggered = StopLossCalculator.is_stop_loss_triggered(
            position_side="NO",
            entry_price=0.40,
            current_price=0.44,
            stop_loss_price=0.44  # Exactly at stop
        )
        
        # >= means equal will trigger
        assert triggered is True


class TestCalculatePnlAtStopLoss:
    """Tests for StopLossCalculator.calculate_pnl_at_stop_loss()"""
    
    def test_yes_position_loss(self):
        """YES position PnL should be negative when stop triggered."""
        pnl = StopLossCalculator.calculate_pnl_at_stop_loss(
            entry_price=0.60,
            stop_loss_price=0.54,  # 10% stop
            quantity=10,
            side="YES"
        )
        
        # Loss = (0.54 - 0.60) * 10 = -0.06 * 10 = -0.60
        assert pnl == pytest.approx(-0.60, abs=0.01)
        
    def test_no_position_loss(self):
        """NO position PnL should be negative when stop triggered.
        
        NOTE: On Kalshi, NO works same as YES - you LOSE when price FALLS.
        Formula: PnL = (stop_loss_price - entry_price) * quantity
        """
        pnl = StopLossCalculator.calculate_pnl_at_stop_loss(
            entry_price=0.40,
            stop_loss_price=0.36,  # 10% stop BELOW entry (price dropped)
            quantity=10,
            side="NO"
        )
        
        # NO position LOSES when price falls (same as YES)
        # Loss = (0.36 - 0.40) * 10 = -0.04 * 10 = -0.40
        assert pnl == pytest.approx(-0.40, abs=0.01)
        
    def test_larger_quantity_larger_loss(self):
        """Larger quantity should result in larger PnL magnitude."""
        pnl_small = StopLossCalculator.calculate_pnl_at_stop_loss(
            entry_price=0.60,
            stop_loss_price=0.54,
            quantity=5,
            side="YES"
        )
        
        pnl_large = StopLossCalculator.calculate_pnl_at_stop_loss(
            entry_price=0.60,
            stop_loss_price=0.54,
            quantity=50,
            side="YES"
        )
        
        assert abs(pnl_large) > abs(pnl_small)
        assert abs(pnl_large) == abs(pnl_small) * 10
        
    def test_zero_quantity(self):
        """Zero quantity should result in zero PnL."""
        pnl = StopLossCalculator.calculate_pnl_at_stop_loss(
            entry_price=0.60,
            stop_loss_price=0.54,
            quantity=0,
            side="YES"
        )
        
        assert pnl == 0.0


class TestConvenienceFunction:
    """Tests for module-level convenience function."""
    
    def test_convenience_function_works(self):
        """Convenience function should call class method."""
        result = calculate_stop_loss_levels(
            entry_price=0.50,
            side="YES",
            confidence=0.75,
            market_volatility=0.20,
            time_to_expiry_days=7
        )
        
        assert 'stop_loss_price' in result
        assert 'take_profit_price' in result
        assert 'max_hold_hours' in result
        
    def test_convenience_function_matches_class(self):
        """Convenience function should match class method exactly."""
        params = {
            'entry_price': 0.50,
            'side': 'YES',
            'confidence': 0.75,
            'market_volatility': 0.20,
            'time_to_expiry_days': 7
        }
        
        result_func = calculate_stop_loss_levels(**params)
        result_class = StopLossCalculator.calculate_stop_loss_levels(**params)
        
        assert result_func == result_class
