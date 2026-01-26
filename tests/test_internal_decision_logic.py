"""
Comprehensive tests for internal_decision_logic module.

Tests all functions:
- make_internal_trading_decision()
- should_skip_market_without_ai()
"""

import pytest
import time
from src.utils.internal_decision_logic import (
    make_internal_trading_decision,
    should_skip_market_without_ai,
    InternalTradingDecision
)


class TestMakeInternalTradingDecision:
    """Tests for make_internal_trading_decision()"""
    
    def test_high_yes_price_near_expiry_buys_yes(self):
        """Near expiry with high YES price should buy YES."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': time.time() + (12 * 3600)  # 12 hours
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "YES"
        assert decision.confidence >= 0.80
        
    def test_low_yes_price_near_expiry_buys_no(self):
        """Near expiry with low YES price should buy NO."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.10,
            'no_price': 0.90,
            'volume': 1000,
            'expiration_ts': time.time() + (12 * 3600)  # 12 hours
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "NO"
        assert decision.confidence >= 0.80
        
    def test_extreme_yes_price_not_near_expiry(self):
        """Extreme YES price (>88%) should buy YES even not near expiry."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.92,
            'no_price': 0.08,
            'volume': 1000,
            'expiration_ts': time.time() + (7 * 24 * 3600)  # 7 days
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "YES"
        
    def test_extreme_no_price_not_near_expiry(self):
        """Extreme NO price (YES < 12%) should buy NO even not near expiry."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.08,
            'no_price': 0.92,
            'volume': 1000,
            'expiration_ts': time.time() + (7 * 24 * 3600)  # 7 days
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "NO"
        
    def test_neutral_market_skips(self):
        """Market with neutral prices should skip."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.50,
            'no_price': 0.50,
            'volume': 1000,
            'expiration_ts': time.time() + (7 * 24 * 3600)  # 7 days
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "SKIP"
        
    def test_decision_has_reasoning(self):
        """Decision should include reasoning string."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': time.time() + (12 * 3600)
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert len(decision.reasoning) > 0
        
    def test_decision_has_limit_price(self):
        """BUY decision should include limit price."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': time.time() + (12 * 3600)
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        if decision.action == "BUY":
            assert decision.limit_price is not None
            assert decision.limit_price > 0
            assert decision.limit_price <= 100  # In cents
            
    def test_missing_market_data_fields(self):
        """Should handle missing market data fields gracefully."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            # Missing yes_price, no_price, volume, expiration_ts
        }
        
        portfolio_data = {'available_balance': 1000}
        
        # Should not raise exception
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision is not None
        assert decision.action in ["BUY", "SKIP"]
        
    def test_skip_decision_has_skip_reasoning(self):
        """SKIP decision should explain why."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.50,
            'no_price': 0.50,
            'volume': 1000,
            'expiration_ts': time.time() + (30 * 24 * 3600)  # 30 days
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "SKIP"
        assert len(decision.reasoning) > 0


class TestShouldSkipMarketWithoutAI:
    """Tests for should_skip_market_without_ai()"""
    
    def test_low_volume_skips(self):
        """Low volume markets with distant expiry should be skipped."""
        # Implementation skips when volume < 200 AND hours_to_expiry > 48
        skip, reason = should_skip_market_without_ai(
            yes_price=0.90,
            no_price=0.10,
            volume=50,  # Very low
            hours_to_expiry=72  # > 48 to trigger low volume skip
        )
        
        assert skip is True
        assert "Low volume" in reason
        
    def test_high_volume_does_not_skip(self):
        """High volume markets should not automatically skip."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.90,
            no_price=0.10,
            volume=10000,
            hours_to_expiry=24
        )
        
        # Should not skip due to volume
        # May skip for other reasons but not volume
        # This test validates volume check works
        assert skip is False  # High volume + extreme price
        
    def test_neutral_price_skips(self):
        """Neutral prices (around 50%) should skip."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.52,
            no_price=0.48,
            volume=5000,
            hours_to_expiry=24
        )
        
        assert skip is True
        assert "uncertain range" in reason
        
    def test_extreme_price_does_not_skip(self):
        """Extreme prices should not skip."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.95,
            no_price=0.05,
            volume=5000,
            hours_to_expiry=24
        )
        
        assert skip is False
        assert "suitable" in reason.lower()
        
    def test_very_short_expiry_does_not_skip(self):
        """Very short expiry with good conditions should not skip."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.85,
            no_price=0.15,
            volume=1000,
            hours_to_expiry=2  # Very close to expiry
        )
        
        assert skip is False
        
    def test_wide_spread_skips(self):
        """Wide spread markets should be skipped."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.65,
            no_price=0.45,  # Spread = 0.65 + 0.45 - 1 = 0.10
            volume=5000,
            hours_to_expiry=24
        )
        
        assert skip is True
        assert "spread" in reason.lower()
        
    def test_tight_spread_does_not_skip(self):
        """Tight spread markets should not skip for spread reason."""
        skip, reason = should_skip_market_without_ai(
            yes_price=0.90,
            no_price=0.11,  # Spread = 0.90 + 0.11 - 1 = 0.01
            volume=5000,
            hours_to_expiry=24
        )
        
        assert skip is False


class TestInternalTradingDecisionDataclass:
    """Tests for InternalTradingDecision dataclass."""
    
    def test_dataclass_creation(self):
        """Should create dataclass with all fields."""
        decision = InternalTradingDecision(
            action="BUY",
            side="YES",
            confidence=0.85,
            limit_price=90,
            reasoning="Test reasoning"
        )
        
        assert decision.action == "BUY"
        assert decision.side == "YES"
        assert decision.confidence == 0.85
        assert decision.limit_price == 90
        assert decision.reasoning == "Test reasoning"
        
    def test_default_values(self):
        """Should have sensible defaults."""
        decision = InternalTradingDecision(
            action="SKIP",
            side="YES",
            confidence=0.5
        )
        
        assert decision.limit_price is None
        assert decision.reasoning == ""
        
    def test_action_values(self):
        """Action should be BUY or SKIP."""
        decision_buy = InternalTradingDecision(
            action="BUY",
            side="YES",
            confidence=0.85
        )
        
        decision_skip = InternalTradingDecision(
            action="SKIP",
            side="NO",
            confidence=0.5
        )
        
        assert decision_buy.action in ["BUY", "SKIP"]
        assert decision_skip.action in ["BUY", "SKIP"]
        
    def test_side_values(self):
        """Side should be YES or NO."""
        decision_yes = InternalTradingDecision(
            action="BUY",
            side="YES",
            confidence=0.85
        )
        
        decision_no = InternalTradingDecision(
            action="BUY",
            side="NO",
            confidence=0.85
        )
        
        assert decision_yes.side in ["YES", "NO"]
        assert decision_no.side in ["YES", "NO"]


class TestEdgeCases:
    """Edge case tests for internal decision logic."""
    
    def test_zero_expiration_ts(self):
        """Should handle zero expiration timestamp."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': 0  # Zero timestamp
        }
        
        portfolio_data = {'available_balance': 1000}
        
        # Should not raise exception
        decision = make_internal_trading_decision(market_data, portfolio_data)
        assert decision is not None
        
    def test_past_expiration_ts(self):
        """Should handle past expiration timestamp."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': time.time() - 3600  # 1 hour ago
        }
        
        portfolio_data = {'available_balance': 1000}
        
        # Should not raise exception
        decision = make_internal_trading_decision(market_data, portfolio_data)
        assert decision is not None
        
    def test_very_low_yes_price(self):
        """Should handle very low YES price."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.01,
            'no_price': 0.99,
            'volume': 1000,
            'expiration_ts': time.time() + (24 * 3600)
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "NO"
        
    def test_very_high_yes_price(self):
        """Should handle very high YES price."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.99,
            'no_price': 0.01,
            'volume': 1000,
            'expiration_ts': time.time() + (24 * 3600)
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert decision.action == "BUY"
        assert decision.side == "YES"
        
    def test_confidence_range(self):
        """Confidence should always be 0-1."""
        market_data = {
            'ticker': 'TEST-MARKET',
            'title': 'Test Market',
            'yes_price': 0.90,
            'no_price': 0.10,
            'volume': 1000,
            'expiration_ts': time.time() + (12 * 3600)
        }
        
        portfolio_data = {'available_balance': 1000}
        
        decision = make_internal_trading_decision(market_data, portfolio_data)
        
        assert 0.0 <= decision.confidence <= 1.0
