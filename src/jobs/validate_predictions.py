"""
Prediction Validation Job

This job checks resolved markets against AI predictions to validate accuracy.
Should be run periodically (e.g., daily) to update the accuracy tracker with outcomes.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from src.utils.database import DatabaseManager
from src.utils.ai_accuracy_tracker import create_accuracy_tracker
from src.clients.kalshi_client import KalshiClient
from src.utils.logging_setup import get_trading_logger


async def validate_recent_predictions(
    db_manager: DatabaseManager,
    kalshi_client: KalshiClient,
    hours_back: int = 48
) -> int:
    """
    Check recent predictions against resolved markets and update accuracy.
    
    Args:
        db_manager: Database manager instance
        kalshi_client: Kalshi API client
        hours_back: How many hours back to check predictions
    
    Returns:
        Number of predictions validated
    """
    logger = get_trading_logger("prediction_validation")
    logger.info(f"Starting prediction validation for last {hours_back} hours")
    
    try:
        # Initialize accuracy tracker
        tracker = await create_accuracy_tracker(db_manager)
        
        # Get recent predictions that haven't been validated yet
        recent_predictions = await tracker.get_recent_predictions(
            hours_back=hours_back,
            only_unvalidated=True
        )
        
        if not recent_predictions:
            logger.info("No unvalidated predictions found")
            return 0
        
        logger.info(f"Found {len(recent_predictions)} unvalidated predictions to check")
        
        validated_count = 0
        for prediction in recent_predictions:
            try:
                # Get current market data
                market_response = await kalshi_client.get_market(prediction.market_id)
                
                if not market_response or 'market' not in market_response:
                    logger.warning(f"Could not get market data for {prediction.market_id}")
                    continue
                
                market_info = market_response['market']
                market_status = market_info.get('status', 'unknown')
                
                # Only validate if market is closed/resolved
                if market_status == 'closed':
                    result = market_info.get('result')
                    
                    if result:
                        # Validate the prediction
                        await tracker.validate_outcome(
                            market_id=prediction.market_id,
                            actual_result=result
                        )
                        
                        validated_count += 1
                        
                        # Log whether prediction was correct
                        was_correct = (prediction.predicted_side == result)
                        logger.info(
                            f"✅ Validated {prediction.market_id}: "
                            f"Predicted {prediction.predicted_side}, "
                            f"Actual {result} "
                            f"({'✓ CORRECT' if was_correct else '✗ INCORRECT'})"
                        )
                    else:
                        logger.debug(f"Market {prediction.market_id} closed but no result yet")
                else:
                    logger.debug(f"Market {prediction.market_id} still {market_status}")
                    
            except Exception as e:
                logger.error(f"Error validating prediction for {prediction.market_id}: {e}")
                continue
        
        logger.info(f"🎯 Validation complete: {validated_count} predictions validated")
        
        # Get updated accuracy metrics
        if validated_count > 0:
            metrics = await tracker.get_accuracy_metrics()
            
            logger.info(
                f"📊 Current Accuracy Metrics:\n"
                f"  Overall Accuracy: {metrics['overall_accuracy']:.1%}\n"
                f"  Total Predictions: {metrics['total_predictions']}\n"
                f"  Validated: {metrics['validated_count']}\n"
                f"  Correct: {metrics['correct_count']}\n"
                f"  Incorrect: {metrics['incorrect_count']}"
            )
            
            # Log accuracy by confidence bracket
            if metrics.get('by_confidence_bracket'):
                logger.info("📈 Accuracy by Confidence Bracket:")
                for bracket in metrics['by_confidence_bracket']:
                    logger.info(
                        f"  {bracket['bracket']}: "
                        f"{bracket['accuracy']:.1%} "
                        f"({bracket['correct']}/{bracket['total']} predictions)"
                    )
            
            # Log accuracy by strategy
            if metrics.get('by_strategy'):
                logger.info("🎯 Accuracy by Strategy:")
                for strategy in metrics['by_strategy']:
                    logger.info(
                        f"  {strategy['strategy']}: "
                        f"{strategy['accuracy']:.1%} "
                        f"({strategy['correct']}/{strategy['total']} predictions)"
                    )
        
        return validated_count
        
    except Exception as e:
        logger.error(f"Error in prediction validation: {e}")
        return 0


async def run_validation_job():
    """
    Main entry point for the validation job.
    Can be run as a standalone script or scheduled.
    """
    logger = get_trading_logger("prediction_validation_job")
    logger.info("🔍 Starting Prediction Validation Job")
    
    db_manager = DatabaseManager()
    kalshi_client = KalshiClient()
    
    try:
        await db_manager.initialize()
        
        # Validate predictions from last 48 hours
        validated_count = await validate_recent_predictions(
            db_manager, kalshi_client, hours_back=48
        )
        
        logger.info(f"✅ Validation job complete: {validated_count} predictions validated")
        
    except Exception as e:
        logger.error(f"Error in validation job: {e}")
    finally:
        await kalshi_client.close()


if __name__ == "__main__":
    """
    Run validation job directly.
    
    Usage:
        python src/jobs/validate_predictions.py
    
    Can also be scheduled via cron or Windows Task Scheduler:
        # Run daily at 2 AM
        0 2 * * * cd /path/to/kalshi-ai-trading-bot && python src/jobs/validate_predictions.py
    """
    from src.utils.logging_setup import setup_logging
    setup_logging()
    asyncio.run(run_validation_job())
