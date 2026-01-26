"""
Internal Decision Logic Module

This module provides rule-based trading decisions without requiring AI API calls.
It serves as a cost-saving fallback when use_ai_for_decisions is set to False.

Strategies implemented:
1. High-Confidence Near-Expiry: Trade markets where price is near extremes (>90% or <10%)
2. Edge-Based Trading: Trade when market spread indicates opportunity
3. Volume/Liquidity Analysis: Favor high-volume, tight-spread markets
4. Mean Reversion: Trade markets that have moved significantly from recent averages
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime
import time

from src.utils.logging_setup import get_trading_logger


@dataclass
class InternalTradingDecision:
    """Represents a trading decision made by internal logic."""
    action: str  # "BUY" or "SKIP"
    side: str    # "YES" or "NO"
    confidence: float  # 0.0 to 1.0
    limit_price: Optional[int] = None
    reasoning: str = ""


def make_internal_trading_decision(
    market_data: dict,
    portfolio_data: dict,
) -> InternalTradingDecision:
    """
    Make a trading decision using internal rule-based logic.
    
    This is a cost-saving alternative to AI-based decisions that uses
    heuristics and market data analysis.
    
    Args:
        market_data: Market information (ticker, title, yes_price, no_price, volume, etc.)
        portfolio_data: Portfolio information (available_balance, etc.)
    
    Returns:
        InternalTradingDecision with action, side, confidence, and reasoning
    """
    logger = get_trading_logger("internal_decision")
    
    try:
        # Extract market data
        yes_price = market_data.get('yes_price', 0.50)
        no_price = market_data.get('no_price', 0.50)
        volume = market_data.get('volume', 0)
        title = market_data.get('title', 'Unknown')
        ticker = market_data.get('ticker', 'Unknown')
        
        # Calculate basic metrics
        spread = abs((yes_price + no_price) - 1.0)  # Ideal spread is 0
        
        # Get time to expiry if available
        expiration_ts = market_data.get('expiration_ts', 0)
        hours_to_expiry = max(0, (expiration_ts - time.time()) / 3600) if expiration_ts else 168
        
        logger.debug(
            f"Internal analysis: {ticker}",
            yes_price=yes_price,
            no_price=no_price,
            volume=volume,
            hours_to_expiry=hours_to_expiry
        )
        
        # Strategy 1: High-Confidence Near-Expiry
        # If market is near expiry and price is extreme, trade toward resolution
        if hours_to_expiry <= 24 and hours_to_expiry > 0:
            if yes_price >= 0.85:
                return InternalTradingDecision(
                    action="BUY",
                    side="YES",
                    confidence=0.85,
                    limit_price=int(yes_price * 100),
                    reasoning=f"Near-expiry high-probability YES (price={yes_price:.2f}, hours_to_expiry={hours_to_expiry:.1f})"
                )
            elif yes_price <= 0.15:
                return InternalTradingDecision(
                    action="BUY",
                    side="NO",
                    confidence=0.85,
                    limit_price=int(no_price * 100),
                    reasoning=f"Near-expiry high-probability NO (price={no_price:.2f}, hours_to_expiry={hours_to_expiry:.1f})"
                )
        
        # Strategy 2: Extreme Price Opportunities (not near expiry)
        # Markets with very extreme prices often have edge
        if yes_price >= 0.88:
            # Very high YES price - likely to resolve YES
            return InternalTradingDecision(
                action="BUY",
                side="YES",
                confidence=0.75,
                limit_price=int(yes_price * 100),
                reasoning=f"Extreme high YES price suggests strong probability (price={yes_price:.2f})"
            )
        elif yes_price <= 0.12:
            # Very low YES price - likely to resolve NO
            return InternalTradingDecision(
                action="BUY",
                side="NO",
                confidence=0.75,
                limit_price=int(no_price * 100),
                reasoning=f"Extreme low YES price suggests strong NO probability (no_price={no_price:.2f})"
            )
        
        # Strategy 3: Tight Spread, High Volume Opportunities
        # Markets with good liquidity and tight spreads in middle range
        if volume >= 500 and spread <= 0.05:
            # High volume, tight spread - good market for trading
            # Use slight contrarian approach on mid-range prices
            if 0.45 <= yes_price <= 0.55:
                # Market is uncertain - skip without AI insight
                return InternalTradingDecision(
                    action="SKIP",
                    side="YES",
                    confidence=0.40,
                    reasoning=f"Market too uncertain (price={yes_price:.2f}), needs AI analysis"
                )
            elif 0.55 < yes_price < 0.75:
                # Moderately bullish - follow momentum
                return InternalTradingDecision(
                    action="BUY",
                    side="YES",
                    confidence=0.60,
                    limit_price=int(yes_price * 100),
                    reasoning=f"High-volume momentum YES (price={yes_price:.2f}, volume={volume})"
                )
            elif 0.25 < yes_price < 0.45:
                # Moderately bearish - follow momentum  
                return InternalTradingDecision(
                    action="BUY",
                    side="NO",
                    confidence=0.60,
                    limit_price=int(no_price * 100),
                    reasoning=f"High-volume momentum NO (price={no_price:.2f}, volume={volume})"
                )
        
        # Strategy 4: Volume-Weighted Opportunities
        # Very high volume markets with moderate prices
        if volume >= 1000:
            if yes_price >= 0.65:
                return InternalTradingDecision(
                    action="BUY",
                    side="YES",
                    confidence=0.65,
                    limit_price=int(yes_price * 100),
                    reasoning=f"Very high volume YES opportunity (volume={volume}, price={yes_price:.2f})"
                )
            elif yes_price <= 0.35:
                return InternalTradingDecision(
                    action="BUY",
                    side="NO",
                    confidence=0.65,
                    limit_price=int(no_price * 100),
                    reasoning=f"Very high volume NO opportunity (volume={volume}, price={no_price:.2f})"
                )
        
        # Default: Skip if no clear opportunity
        return InternalTradingDecision(
            action="SKIP",
            side="YES",
            confidence=0.30,
            reasoning=f"No clear internal logic opportunity (price={yes_price:.2f}, volume={volume})"
        )
        
    except Exception as e:
        logger.error(f"Error in internal decision logic: {e}")
        return InternalTradingDecision(
            action="SKIP",
            side="YES",
            confidence=0.0,
            reasoning=f"Error in internal logic: {str(e)}"
        )


def get_internal_probability_estimate(
    market_price: float,
    volume: int,
    hours_to_expiry: float = 168.0
) -> Tuple[Optional[float], Optional[float]]:
    """
    Get a probability and confidence estimate without AI.
    
    This is used as a fallback for portfolio optimization when AI is disabled.
    Uses market price as the probability estimate with adjustments based on
    volume and time to expiry.
    
    Args:
        market_price: Current market price (0-1 scale)
        volume: Trading volume
        hours_to_expiry: Hours until market expires
    
    Returns:
        Tuple of (probability, confidence) or (None, None) if can't estimate
    """
    try:
        # Base probability is the market price itself
        # (Efficient market hypothesis - market price reflects true probability)
        probability = market_price
        
        # Base confidence in our estimate
        base_confidence = 0.50
        
        # Adjust confidence based on volume (more volume = more reliable price)
        if volume >= 2000:
            volume_boost = 0.15
        elif volume >= 1000:
            volume_boost = 0.10
        elif volume >= 500:
            volume_boost = 0.05
        else:
            volume_boost = 0.0
        
        # Adjust confidence based on how extreme the price is
        # Extreme prices are more likely to be accurate
        price_extremity = abs(market_price - 0.50) * 2  # 0 at 50%, 1 at 0% or 100%
        extremity_boost = price_extremity * 0.10
        
        # Near-expiry markets have more certain outcomes
        if hours_to_expiry <= 24:
            time_boost = 0.15
        elif hours_to_expiry <= 72:
            time_boost = 0.05
        else:
            time_boost = 0.0
        
        # Calculate final confidence (cap at 0.75 without AI)
        confidence = min(0.75, base_confidence + volume_boost + extremity_boost + time_boost)
        
        # For extreme prices, adjust probability slightly toward the extreme
        # (Markets tend to underestimate extreme outcomes)
        if probability >= 0.80:
            probability = min(0.95, probability + 0.02)
        elif probability <= 0.20:
            probability = max(0.05, probability - 0.02)
        
        return probability, confidence
        
    except Exception:
        return None, None


def should_skip_market_without_ai(
    yes_price: float,
    no_price: float,
    volume: int,
    hours_to_expiry: float
) -> Tuple[bool, str]:
    """
    Determine if a market should be skipped when AI is disabled.
    
    Markets in the "uncertain" range (40-60%) require AI analysis to have
    any meaningful edge. Without AI, we skip these.
    
    Args:
        yes_price: Current YES price
        no_price: Current NO price
        volume: Trading volume
        hours_to_expiry: Hours until expiry
    
    Returns:
        Tuple of (should_skip, reason)
    """
    # Skip uncertain markets (40-60% range) - need AI for these
    if 0.40 <= yes_price <= 0.60:
        return True, f"Market in uncertain range ({yes_price:.2f}), requires AI analysis"
    
    # Skip low volume markets when not near expiry
    if volume < 200 and hours_to_expiry > 48:
        return True, f"Low volume ({volume}) with distant expiry, too risky without AI"
    
    # Skip markets with wide spreads
    spread = abs((yes_price + no_price) - 1.0)
    if spread > 0.08:
        return True, f"Wide spread ({spread:.2f}), poor execution without AI timing"
    
    # Don't skip - market has clear opportunity
    return False, "Market suitable for internal logic trading"
