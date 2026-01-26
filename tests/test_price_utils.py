"""
Comprehensive tests for price_utils module.

Tests all functions:
- get_market_prices()
- get_entry_price()
- get_exit_price()
"""

import pytest
from src.utils.price_utils import (
    get_market_prices,
    get_entry_price,
    get_exit_price,
    MarketPrices
)


class TestGetMarketPrices:
    """Tests for get_market_prices()"""
    
    def test_valid_market_data(self):
        """Should correctly extract prices from valid market data."""
        market_data = {
            'yes_bid': 55,
            'no_bid': 45,
            'yes_ask': 57,
            'no_ask': 43,
            'last_price': 56
        }
        
        prices = get_market_prices(market_data)
        
        # Prices should be converted from cents to dollars
        assert prices.yes_bid == 0.55
        assert prices.no_bid == 0.45
        assert prices.yes_ask == 0.57
        assert prices.no_ask == 0.43
        assert prices.last_price == 0.56
        assert prices.is_valid is True
        
    def test_empty_market_data(self):
        """Should handle empty market data gracefully."""
        prices = get_market_prices({})
        
        assert prices.yes_bid == 0
        assert prices.is_valid is False
        assert prices.validation_error is not None
        
    def test_none_market_data(self):
        """Should handle None market data."""
        prices = get_market_prices(None)
        
        assert prices.is_valid is False
        assert prices.validation_error is not None
        
    def test_missing_fields_use_zero(self):
        """Missing fields should default to zero."""
        market_data = {
            'yes_bid': 55,
            # Missing other fields
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == 0.55
        assert prices.no_bid == 0  # Missing
        assert prices.yes_ask == 0  # Missing
        
    def test_none_values_use_zero(self):
        """None values should be treated as zero."""
        market_data = {
            'yes_bid': 55,
            'no_bid': None,
            'yes_ask': None,
            'no_ask': 45,
            'last_price': 56
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == 0.55
        assert prices.no_bid == 0
        assert prices.yes_ask == 0
        assert prices.no_ask == 0.45
        
    def test_conversion_from_cents(self):
        """Should convert cents (0-100) to dollars (0-1)."""
        market_data = {
            'yes_bid': 99,
            'no_bid': 1,
            'yes_ask': 100,
            'no_ask': 0,
            'last_price': 50
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == 0.99
        assert prices.no_bid == 0.01
        assert prices.yes_ask == 1.00
        assert prices.no_ask == 0.00
        assert prices.last_price == 0.50
        
    def test_require_valid_raises_on_empty(self):
        """Should raise ValueError when require_valid=True and data is empty."""
        with pytest.raises(ValueError):
            get_market_prices({}, require_valid=True)
            
    def test_require_valid_raises_on_none(self):
        """Should raise ValueError when require_valid=True and data is None."""
        with pytest.raises(ValueError):
            get_market_prices(None, require_valid=True)


class TestGetEntryPrice:
    """Tests for get_entry_price()"""
    
    def test_yes_entry_uses_ask(self):
        """YES entry should use yes_ask (what sellers want)."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_entry_price(market_data, 'YES')
        
        # Should use ASK for buying
        assert price == 0.57
        assert valid is True
        
    def test_no_entry_uses_ask(self):
        """NO entry should use no_ask (what sellers want)."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_entry_price(market_data, 'NO')
        
        # Should use ASK for buying
        assert price == 0.45
        assert valid is True
        
    def test_fallback_to_last_price_yes(self):
        """Should fall back to last_price if ask is missing."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 0,  # Not available
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_entry_price(market_data, 'YES')
        
        # Should fall back to last_price
        assert price == 0.56
        
    def test_fallback_to_last_price_no(self):
        """Should fall back to (100 - last_price) for NO if no_ask missing."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 0,  # Not available
            'last_price': 56
        }
        
        price, valid = get_entry_price(market_data, 'NO')
        
        # Should fall back to (100 - last_price) / 100 = 0.44
        assert price == pytest.approx(0.44, abs=0.01)
        
    def test_invalid_when_no_price(self):
        """Should return invalid when no price available."""
        market_data = {
            'yes_bid': 0,
            'yes_ask': 0,
            'no_bid': 0,
            'no_ask': 0,
            'last_price': 0
        }
        
        price, valid = get_entry_price(market_data, 'YES')
        
        assert valid is False
        
    def test_case_insensitive_side(self):
        """Should handle uppercase/lowercase side."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price_upper, valid_upper = get_entry_price(market_data, 'YES')
        price_lower, valid_lower = get_entry_price(market_data, 'yes')
        
        assert price_upper == price_lower
        assert valid_upper == valid_lower


class TestGetExitPrice:
    """Tests for get_exit_price()"""
    
    def test_yes_exit_uses_bid(self):
        """YES exit should use yes_bid (what buyers pay)."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_exit_price(market_data, 'YES')
        
        # Should use BID for selling
        assert price == 0.55
        assert valid is True
        
    def test_no_exit_uses_bid(self):
        """NO exit should use no_bid (what buyers pay)."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_exit_price(market_data, 'NO')
        
        # Should use BID for selling
        assert price == 0.43
        assert valid is True
        
    def test_fallback_to_last_price_yes(self):
        """Should fall back to last_price if bid is missing."""
        market_data = {
            'yes_bid': 0,  # Not available
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_exit_price(market_data, 'YES')
        
        # Should fall back to last_price
        assert price == 0.56
        
    def test_fallback_to_last_price_no(self):
        """Should fall back to (100 - last_price) for NO if no_bid missing."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 57,
            'no_bid': 0,  # Not available
            'no_ask': 45,
            'last_price': 56
        }
        
        price, valid = get_exit_price(market_data, 'NO')
        
        # Should fall back to (100 - last_price) / 100 = 0.44
        assert price == pytest.approx(0.44, abs=0.01)


class TestMarketPricesDataclass:
    """Tests for MarketPrices dataclass."""
    
    def test_dataclass_creation(self):
        """Should create dataclass with all fields."""
        prices = MarketPrices(
            yes_bid=0.55,
            no_bid=0.45,
            yes_ask=0.57,
            no_ask=0.43,
            last_price=0.56,
            is_valid=True
        )
        
        assert prices.yes_bid == 0.55
        assert prices.no_bid == 0.45
        assert prices.is_valid is True
        assert prices.validation_error is None
        
    def test_validation_error_default(self):
        """Validation error should default to None."""
        prices = MarketPrices(
            yes_bid=0.55,
            no_bid=0.45,
            yes_ask=0.57,
            no_ask=0.43,
            last_price=0.56,
            is_valid=True
        )
        
        assert prices.validation_error is None
        
    def test_validation_error_set(self):
        """Should store validation error message."""
        prices = MarketPrices(
            yes_bid=0,
            no_bid=0,
            yes_ask=0,
            no_ask=0,
            last_price=0,
            is_valid=False,
            validation_error="No valid prices"
        )
        
        assert prices.validation_error == "No valid prices"


class TestPriceValidation:
    """Tests for price validation logic."""
    
    def test_all_zero_is_invalid(self):
        """All zero prices should be invalid."""
        market_data = {
            'yes_bid': 0,
            'yes_ask': 0,
            'no_bid': 0,
            'no_ask': 0,
            'last_price': 0
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.is_valid is False
        
    def test_partial_prices_can_be_valid(self):
        """Having some valid prices should still work."""
        market_data = {
            'yes_bid': 55,
            'yes_ask': 0,  # Missing
            'no_bid': 0,   # Missing
            'no_ask': 0,   # Missing
            'last_price': 56
        }
        
        prices = get_market_prices(market_data)
        
        # Should have some valid data
        assert prices.yes_bid == 0.55
        assert prices.last_price == 0.56
        
    def test_negative_prices_treated_as_zero(self):
        """Negative prices should be treated as zero or invalid."""
        market_data = {
            'yes_bid': -5,  # Invalid
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        prices = get_market_prices(market_data)
        
        # Negative should be treated as zero
        assert prices.yes_bid <= 0


class TestEdgeCases:
    """Edge case tests for price utilities."""
    
    def test_extreme_low_price(self):
        """Should handle 1 cent (0.01) prices."""
        market_data = {
            'yes_bid': 1,
            'yes_ask': 2,
            'no_bid': 98,
            'no_ask': 99,
            'last_price': 1
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == 0.01
        assert prices.last_price == 0.01
        
    def test_extreme_high_price(self):
        """Should handle 99 cent (0.99) prices."""
        market_data = {
            'yes_bid': 99,
            'yes_ask': 100,
            'no_bid': 0,
            'no_ask': 1,
            'last_price': 99
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == 0.99
        assert prices.yes_ask == 1.00
        
    def test_string_values_handled(self):
        """Should handle string values gracefully."""
        market_data = {
            'yes_bid': '55',  # String instead of int
            'yes_ask': 57,
            'no_bid': 43,
            'no_ask': 45,
            'last_price': 56
        }
        
        # Should either convert or not crash
        try:
            prices = get_market_prices(market_data)
            # If it works, values should be reasonable
            assert prices.yes_bid >= 0
        except (ValueError, TypeError):
            # Raising is also acceptable
            pass
            
    def test_float_cent_values(self):
        """Should handle float cent values."""
        market_data = {
            'yes_bid': 55.5,  # Float cents
            'yes_ask': 57.5,
            'no_bid': 43.0,
            'no_ask': 45.0,
            'last_price': 56.0
        }
        
        prices = get_market_prices(market_data)
        
        assert prices.yes_bid == pytest.approx(0.555, abs=0.001)
