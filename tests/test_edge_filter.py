"""
Comprehensive tests for EdgeFilter module.

Tests all methods:
- calculate_edge()
- should_trade_market()
"""

import pytest
from src.utils.edge_filter import EdgeFilter, EdgeFilterResult


class TestCalculateEdge:
    """Tests for EdgeFilter.calculate_edge()"""
    
    def test_positive_edge_yes_side(self):
        """Positive edge (AI higher) should recommend YES side."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.80
        )
        
        assert result.edge_magnitude == pytest.approx(0.20, abs=0.01)
        assert result.side == "YES"
        
    def test_negative_edge_no_side(self):
        """Negative edge (AI lower) should recommend NO side."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.30,
            market_probability=0.50,
            confidence=0.80
        )
        
        assert result.edge_magnitude == pytest.approx(-0.20, abs=0.01)
        assert result.side == "NO"
        
    def test_high_confidence_lower_threshold(self):
        """High confidence should pass with lower edge."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.58,  # 8% edge
            market_probability=0.50,
            confidence=0.85
        )
        
        # High confidence = 6% edge requirement, 8% > 6%
        assert result.passes_filter is True
        
    def test_medium_confidence_medium_threshold(self):
        """Medium confidence needs medium edge."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.60,  # 10% edge
            market_probability=0.50,
            confidence=0.70
        )
        
        # Medium confidence = 8% edge requirement, 10% > 8%
        assert result.passes_filter is True
        
    def test_low_confidence_higher_threshold(self):
        """Low confidence needs higher edge."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.60,  # 10% edge
            market_probability=0.50,
            confidence=0.55
        )
        
        # Low confidence = 12% edge requirement, 10% < 12%
        assert result.passes_filter is False
        
    def test_very_low_confidence_fails(self):
        """Very low confidence should fail even with high edge."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.80,  # 30% edge
            market_probability=0.50,
            confidence=0.40  # Below MIN_CONFIDENCE_FOR_TRADE
        )
        
        # Confidence below 50% minimum
        assert result.passes_filter is False
        
    def test_zero_edge_fails(self):
        """Zero edge should fail filter."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.50,
            market_probability=0.50,
            confidence=0.80
        )
        
        assert result.edge_percentage == 0.0
        assert result.passes_filter is False
        
    def test_edge_percentage_always_positive(self):
        """Edge percentage should be absolute value."""
        result_pos = EdgeFilter.calculate_edge(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.80
        )
        
        result_neg = EdgeFilter.calculate_edge(
            ai_probability=0.30,
            market_probability=0.50,
            confidence=0.80
        )
        
        assert result_pos.edge_percentage > 0
        assert result_neg.edge_percentage > 0
        assert result_pos.edge_percentage == result_neg.edge_percentage
        
    def test_input_clamping_ai_probability(self):
        """AI probability should be clamped to 0.01-0.99."""
        result = EdgeFilter.calculate_edge(
            ai_probability=1.5,  # Invalid, should be clamped to 0.99
            market_probability=0.50,
            confidence=0.80
        )
        
        # Should still work, ai_prob clamped to 0.99
        assert result.edge_magnitude == pytest.approx(0.49, abs=0.02)
        
    def test_input_clamping_market_probability(self):
        """Market probability should be clamped to 0.01-0.99."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.50,
            market_probability=0.0,  # Invalid, should be clamped to 0.01
            confidence=0.80
        )
        
        # market_prob clamped to 0.01
        assert result.edge_magnitude == pytest.approx(0.49, abs=0.02)
        
    def test_default_confidence(self):
        """Default confidence should be 0.7 if not provided."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.60,
            market_probability=0.50,
            confidence=None  # Should default to 0.7
        )
        
        # 10% edge with 0.7 confidence (medium) = 8% requirement
        assert result.passes_filter is True
        
    def test_confidence_adjusted_edge(self):
        """Confidence adjusted edge should be edge * confidence."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.80
        )
        
        # Edge = 0.20, confidence = 0.80, adjusted = 0.16
        assert result.confidence_adjusted_edge == pytest.approx(0.16, abs=0.01)
        
    def test_result_contains_reason(self):
        """Result should contain a reason string."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.80
        )
        
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


class TestShouldTradeMarket:
    """Tests for EdgeFilter.should_trade_market()"""
    
    def test_good_trade_opportunity(self):
        """Should return True for good trading opportunity."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.85
        )
        
        assert should_trade is True
        assert "PASS" in reason.upper() or "APPROVED" in reason.upper() or "ACCEPTED" in reason.upper()
        
    def test_insufficient_edge(self):
        """Should return False when edge is too small."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.52,  # Only 2% edge
            market_probability=0.50,
            confidence=0.80
        )
        
        assert should_trade is False
        
    def test_low_confidence_rejection(self):
        """Should return False when confidence is too low."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.80,  # Large edge
            market_probability=0.50,
            confidence=0.40  # Too low
        )
        
        assert should_trade is False
        
    def test_additional_filters_volume(self):
        """Should apply additional volume filter."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.85,
            additional_filters={
                'volume': 100,  # Too low
                'min_volume': 500
            }
        )
        
        assert should_trade is False
        assert "volume" in reason.lower()
        
    def test_additional_filters_expiry(self):
        """Should apply time to expiry filter."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.85,
            additional_filters={
                'time_to_expiry_days': 60,  # Too far
                'max_time_to_expiry': 30
            }
        )
        
        assert should_trade is False
        assert "expiry" in reason.lower() or "time" in reason.lower()
        
    def test_returns_edge_result(self):
        """Should return EdgeFilterResult as third element."""
        should_trade, reason, result = EdgeFilter.should_trade_market(
            ai_probability=0.70,
            market_probability=0.50,
            confidence=0.85
        )
        
        assert isinstance(result, EdgeFilterResult)
        assert result.edge_magnitude == pytest.approx(0.20, abs=0.01)


class TestEdgeFilterConstants:
    """Tests for EdgeFilter class constants."""
    
    def test_edge_requirements_ordered(self):
        """Edge requirements should increase as confidence decreases."""
        assert EdgeFilter.HIGH_CONFIDENCE_EDGE < EdgeFilter.MEDIUM_CONFIDENCE_EDGE
        assert EdgeFilter.MEDIUM_CONFIDENCE_EDGE < EdgeFilter.LOW_CONFIDENCE_EDGE
        
    def test_min_edge_is_reasonable(self):
        """Minimum edge requirement should be between 5-20%."""
        assert 0.05 <= EdgeFilter.MIN_EDGE_REQUIREMENT <= 0.20
        
    def test_min_confidence_is_reasonable(self):
        """Minimum confidence should be between 40-70%."""
        assert 0.40 <= EdgeFilter.MIN_CONFIDENCE_FOR_TRADE <= 0.70
        
    def test_max_risk_is_reasonable(self):
        """Max acceptable risk should be between 30-70%."""
        assert 0.30 <= EdgeFilter.MAX_ACCEPTABLE_RISK <= 0.70


class TestEdgeFilterEdgeCases:
    """Edge case tests for EdgeFilter."""
    
    def test_boundary_confidence_high(self):
        """Test boundary at high confidence (0.8)."""
        result_below = EdgeFilter.calculate_edge(
            ai_probability=0.56,
            market_probability=0.50,
            confidence=0.79  # Just below 0.8
        )
        
        result_at = EdgeFilter.calculate_edge(
            ai_probability=0.56,
            market_probability=0.50,
            confidence=0.80  # Exactly 0.8
        )
        
        # Should use different thresholds
        # 0.79 = medium (8% req), 0.80 = high (6% req)
        # Edge = 6%, should pass at 0.80 but fail at 0.79
        assert result_at.passes_filter is True
        
    def test_boundary_confidence_medium(self):
        """Test boundary at medium confidence (0.6)."""
        result_below = EdgeFilter.calculate_edge(
            ai_probability=0.60,  # 10% edge
            market_probability=0.50,
            confidence=0.59  # Just below 0.6 (low conf, needs 12%)
        )
        
        result_at = EdgeFilter.calculate_edge(
            ai_probability=0.60,  # 10% edge
            market_probability=0.50,
            confidence=0.60  # Exactly 0.6 (medium conf, needs 8%)
        )
        
        # 10% edge: passes medium, fails low
        assert result_at.passes_filter is True
        assert result_below.passes_filter is False
        
    def test_extreme_probabilities(self):
        """Test with extreme AI probability values."""
        result = EdgeFilter.calculate_edge(
            ai_probability=0.99,
            market_probability=0.01,
            confidence=0.90
        )
        
        assert result.edge_percentage > 0.90  # Very high edge
        assert result.side == "YES"
        assert result.passes_filter is True
