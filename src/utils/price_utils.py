"""
Price Utility Functions for Kalshi API Integration

This module provides centralized, validated price extraction from Kalshi API responses.
CRITICAL: The Kalshi API uses yes_bid/no_bid/yes_ask/no_ask/last_price fields.
          NOT yes_price/no_price (which don't exist!)

Usage:
    from src.utils.price_utils import get_market_prices, get_entry_price, get_exit_price
    
    prices = get_market_prices(market_data)
    entry = get_entry_price(market_data, side='YES')
    exit_price = get_exit_price(market_data, side='YES')
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from src.utils.logging_setup import get_trading_logger

logger = get_trading_logger("price_utils")


@dataclass
class MarketPrices:
    """Validated market prices extracted from Kalshi API response."""
    yes_bid: float  # Highest buy price for YES (in dollars, 0-1)
    no_bid: float   # Highest buy price for NO (in dollars, 0-1)
    yes_ask: float  # Lowest sell price for YES (in dollars, 0-1)
    no_ask: float   # Lowest sell price for NO (in dollars, 0-1)
    last_price: float  # Last traded price (in dollars, 0-1)
    is_valid: bool  # Whether prices are valid for trading
    validation_error: Optional[str] = None


def get_market_prices(market_data: Dict, require_valid: bool = False) -> MarketPrices:
    """
    Extract and validate market prices from Kalshi API response.
    
    Args:
        market_data: The 'market' object from Kalshi API response
        require_valid: If True, raises ValueError when prices are invalid
        
    Returns:
        MarketPrices object with all price fields (in dollars, 0-1 range)
        
    IMPORTANT: Kalshi API returns prices in CENTS (0-100).
               This function converts to DOLLARS (0-1).
               
    API Field Names (correct):
        - yes_bid: Highest buy price for YES
        - no_bid: Highest buy price for NO  
        - yes_ask: Lowest sell price for YES
        - no_ask: Lowest sell price for NO
        - last_price: Last traded price
        
    WRONG Field Names (DO NOT USE):
        - yes_price: DOES NOT EXIST
        - no_price: DOES NOT EXIST
    """
    if not market_data:
        error = "Empty market_data provided"
        logger.warning(f"Price extraction failed: {error}")
        if require_valid:
            raise ValueError(error)
        return MarketPrices(
            yes_bid=0, no_bid=0, yes_ask=0, no_ask=0, 
            last_price=0, is_valid=False, validation_error=error
        )
    
    # Extract prices in cents (Kalshi API format)
    yes_bid_cents = market_data.get('yes_bid', 0) or 0
    no_bid_cents = market_data.get('no_bid', 0) or 0
    yes_ask_cents = market_data.get('yes_ask', 0) or 0
    no_ask_cents = market_data.get('no_ask', 0) or 0
    last_price_cents = market_data.get('last_price', 0) or 0
    
    # Convert to dollars (0-1 range)
    yes_bid = yes_bid_cents / 100
    no_bid = no_bid_cents / 100
    yes_ask = yes_ask_cents / 100
    no_ask = no_ask_cents / 100
    last_price = last_price_cents / 100
    
    # Validate prices
    validation_error = None
    is_valid = True
    
    # Check if we have at least one valid price source
    if yes_bid <= 0 and yes_ask <= 0 and last_price <= 0:
        validation_error = f"No valid YES prices: bid={yes_bid_cents}¢, ask={yes_ask_cents}¢, last={last_price_cents}¢"
        is_valid = False
    
    if no_bid <= 0 and no_ask <= 0 and last_price <= 0:
        if validation_error:
            validation_error += " AND no valid NO prices"
        else:
            validation_error = f"No valid NO prices: bid={no_bid_cents}¢, ask={no_ask_cents}¢"
        is_valid = False
    
    # Sanity check: prices should sum to approximately 100 cents
    if is_valid and yes_bid > 0 and no_bid > 0:
        price_sum = yes_bid + no_bid
        if not (0.90 <= price_sum <= 1.10):  # Allow 10% tolerance
            logger.warning(
                f"Price sanity check warning: YES_bid({yes_bid:.2f}) + NO_bid({no_bid:.2f}) = {price_sum:.2f} (expected ~1.00)"
            )
    
    if validation_error:
        logger.warning(f"Price validation issue: {validation_error}")
        if require_valid:
            raise ValueError(validation_error)
    
    return MarketPrices(
        yes_bid=yes_bid,
        no_bid=no_bid,
        yes_ask=yes_ask,
        no_ask=no_ask,
        last_price=last_price,
        is_valid=is_valid,
        validation_error=validation_error
    )


def get_entry_price(market_data: Dict, side: str) -> Tuple[float, bool]:
    """
    Get the entry price for a position (what you pay to buy).
    
    For BUYING, use the ASK price (what sellers are asking).
    Falls back to last_price if ask not available.
    
    Args:
        market_data: The 'market' object from Kalshi API
        side: 'YES' or 'NO'
        
    Returns:
        Tuple of (price_in_dollars, is_valid)
        
    Example:
        price, valid = get_entry_price(market_data, 'YES')
        if valid:
            place_order(price=price)
    """
    prices = get_market_prices(market_data)
    
    side_upper = side.upper()
    
    if side_upper == 'YES':
        # For buying YES, use yes_ask (what sellers want)
        if prices.yes_ask > 0:
            return prices.yes_ask, True
        elif prices.yes_bid > 0:
            # Fallback to bid (less ideal, but better than nothing)
            return prices.yes_bid, True
        elif prices.last_price > 0:
            return prices.last_price, True
    else:
        # For buying NO, use no_ask
        if prices.no_ask > 0:
            return prices.no_ask, True
        elif prices.no_bid > 0:
            return prices.no_bid, True
        elif prices.last_price > 0:
            # For NO, last_price is typically YES price, so invert
            return 1.0 - prices.last_price, True
    
    logger.error(f"Could not determine valid entry price for {side}: {prices}")
    return 0, False


def get_exit_price(market_data: Dict, side: str) -> Tuple[float, bool]:
    """
    Get the exit price for a position (what you receive when selling).
    
    For SELLING, use the BID price (what buyers are offering).
    Falls back to last_price if bid not available.
    
    Args:
        market_data: The 'market' object from Kalshi API
        side: 'YES' or 'NO'
        
    Returns:
        Tuple of (price_in_dollars, is_valid)
        
    Example:
        price, valid = get_exit_price(market_data, 'YES')
        if valid:
            record_exit(price=price)
    """
    prices = get_market_prices(market_data)
    
    side_upper = side.upper()
    
    if side_upper == 'YES':
        # For selling YES, use yes_bid (what buyers offer)
        if prices.yes_bid > 0:
            return prices.yes_bid, True
        elif prices.yes_ask > 0:
            # Fallback to ask (less ideal, but better than 0)
            return prices.yes_ask, True
        elif prices.last_price > 0:
            return prices.last_price, True
    else:
        # For selling NO, use no_bid
        if prices.no_bid > 0:
            return prices.no_bid, True
        elif prices.no_ask > 0:
            return prices.no_ask, True
        elif prices.last_price > 0:
            return 1.0 - prices.last_price, True
    
    logger.error(f"Could not determine valid exit price for {side}: {prices}")
    return 0, False


def get_current_price(market_data: Dict, side: str) -> Tuple[float, bool]:
    """
    Get the current market price for a side (for P&L calculations).
    
    Uses the midpoint between bid and ask if both available,
    otherwise falls back to bid or last_price.
    
    Args:
        market_data: The 'market' object from Kalshi API
        side: 'YES' or 'NO'
        
    Returns:
        Tuple of (price_in_dollars, is_valid)
    """
    prices = get_market_prices(market_data)
    
    side_upper = side.upper()
    
    if side_upper == 'YES':
        if prices.yes_bid > 0 and prices.yes_ask > 0:
            # Midpoint for best estimate
            return (prices.yes_bid + prices.yes_ask) / 2, True
        elif prices.yes_bid > 0:
            return prices.yes_bid, True
        elif prices.yes_ask > 0:
            return prices.yes_ask, True
        elif prices.last_price > 0:
            return prices.last_price, True
    else:
        if prices.no_bid > 0 and prices.no_ask > 0:
            return (prices.no_bid + prices.no_ask) / 2, True
        elif prices.no_bid > 0:
            return prices.no_bid, True
        elif prices.no_ask > 0:
            return prices.no_ask, True
        elif prices.last_price > 0:
            return 1.0 - prices.last_price, True
    
    logger.error(f"Could not determine current price for {side}: {prices}")
    return 0, False


def validate_price_for_trade(price: float, side: str, action: str = 'buy') -> bool:
    """
    Validate that a price is reasonable for trading.
    
    Args:
        price: Price in dollars (0-1 range)
        side: 'YES' or 'NO'
        action: 'buy' or 'sell'
        
    Returns:
        True if price is valid for trading
    """
    # Price must be in valid range
    if price <= 0 or price >= 1:
        logger.warning(f"Invalid price {price} for {action} {side}: outside (0,1) range")
        return False
    
    # Price should be reasonable (not exactly 0.5 which is suspicious)
    if price == 0.5:
        logger.warning(f"Suspicious price 0.50 for {action} {side}: may be a fallback value")
        return False
    
    return True


# Backward compatibility aliases
def extract_yes_price(market_data: Dict, for_entry: bool = True) -> float:
    """
    DEPRECATED: Use get_entry_price or get_exit_price instead.
    
    This function is provided for backward compatibility only.
    """
    logger.warning("extract_yes_price is deprecated - use get_entry_price or get_exit_price")
    if for_entry:
        price, _ = get_entry_price(market_data, 'YES')
    else:
        price, _ = get_exit_price(market_data, 'YES')
    return price


def extract_no_price(market_data: Dict, for_entry: bool = True) -> float:
    """
    DEPRECATED: Use get_entry_price or get_exit_price instead.
    """
    logger.warning("extract_no_price is deprecated - use get_entry_price or get_exit_price")
    if for_entry:
        price, _ = get_entry_price(market_data, 'NO')
    else:
        price, _ = get_exit_price(market_data, 'NO')
    return price
