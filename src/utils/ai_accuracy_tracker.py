"""
AI Accuracy Tracker

Tracks AI prediction accuracy to validate model reliability and identify
when predictions are trustworthy vs when they're unreliable.

Critical for determining if Grok-4 can achieve >60% accuracy requirement.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import aiosqlite

from src.utils.logging_setup import get_trading_logger
from src.utils.database import DatabaseManager


@dataclass
class AIPrediction:
    """Represents an AI prediction for tracking."""
    market_id: str
    prediction_timestamp: datetime
    predicted_probability: float
    confidence: float
    predicted_side: str  # "YES" or "NO"
    market_price: float
    edge_magnitude: float
    strategy: str
    
    # Validation fields (filled after market resolves)
    actual_result: Optional[str] = None  # "YES", "NO", or "VOID"
    was_correct: Optional[bool] = None
    validation_timestamp: Optional[datetime] = None
    
    # Additional metadata
    volume: Optional[float] = None
    time_to_expiry_hours: Optional[float] = None
    id: Optional[int] = None


class AIAccuracyTracker:
    """
    Track and validate AI prediction accuracy over time.
    
    Usage:
        tracker = AIAccuracyTracker(db_manager)
        
        # When making prediction:
        await tracker.log_prediction(
            market_id="TRUMPWIN-2024",
            predicted_probability=0.65,
            confidence=0.75,
            predicted_side="YES",
            market_price=0.55,
            edge_magnitude=0.10,
            strategy="portfolio_optimization"
        )
        
        # After market resolves:
        await tracker.validate_outcome(market_id="TRUMPWIN-2024", actual_result="YES")
        
        # Get accuracy metrics:
        metrics = await tracker.get_accuracy_metrics(days_back=7)
        print(f"7-day accuracy: {metrics['overall_accuracy']:.1%}")
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize accuracy tracker.
        
        Args:
            db_manager: DatabaseManager instance for persistence
        """
        self.db_manager = db_manager
        self.logger = get_trading_logger("ai_accuracy_tracker")
    
    async def initialize(self):
        """Initialize database schema for AI predictions."""
        async with aiosqlite.connect(self.db_manager.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    prediction_timestamp TEXT NOT NULL,
                    predicted_probability REAL NOT NULL,
                    confidence REAL NOT NULL,
                    predicted_side TEXT NOT NULL,
                    market_price REAL NOT NULL,
                    edge_magnitude REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    actual_result TEXT,
                    was_correct INTEGER,
                    validation_timestamp TEXT,
                    volume REAL,
                    time_to_expiry_hours REAL
                )
            """)
            
            # Create indices for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_predictions_market_id 
                ON ai_predictions(market_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_predictions_timestamp 
                ON ai_predictions(prediction_timestamp)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_predictions_strategy 
                ON ai_predictions(strategy)
            """)
            
            await db.commit()
            
            self.logger.info("AI predictions table initialized successfully")
    
    async def log_prediction(
        self,
        market_id: str,
        predicted_probability: float,
        confidence: float,
        predicted_side: str,
        market_price: float,
        edge_magnitude: float,
        strategy: str,
        volume: Optional[float] = None,
        time_to_expiry_hours: Optional[float] = None
    ) -> int:
        """
        Log an AI prediction for later validation.
        
        Args:
            market_id: Market identifier
            predicted_probability: AI predicted probability (0.0-1.0)
            confidence: AI confidence level (0.0-1.0)
            predicted_side: Predicted side ("YES" or "NO")
            market_price: Current market price at prediction time
            edge_magnitude: Calculated edge (predicted - market)
            strategy: Strategy making the prediction
            volume: Market volume (optional)
            time_to_expiry_hours: Hours until expiry (optional)
            
        Returns:
            Prediction ID
        """
        prediction = AIPrediction(
            market_id=market_id,
            prediction_timestamp=datetime.now(),
            predicted_probability=predicted_probability,
            confidence=confidence,
            predicted_side=predicted_side,
            market_price=market_price,
            edge_magnitude=edge_magnitude,
            strategy=strategy,
            volume=volume,
            time_to_expiry_hours=time_to_expiry_hours
        )
        
        pred_dict = asdict(prediction)
        pred_dict['prediction_timestamp'] = prediction.prediction_timestamp.isoformat()
        
        async with aiosqlite.connect(self.db_manager.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO ai_predictions (
                    market_id, prediction_timestamp, predicted_probability,
                    confidence, predicted_side, market_price, edge_magnitude,
                    strategy, volume, time_to_expiry_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pred_dict['market_id'],
                pred_dict['prediction_timestamp'],
                pred_dict['predicted_probability'],
                pred_dict['confidence'],
                pred_dict['predicted_side'],
                pred_dict['market_price'],
                pred_dict['edge_magnitude'],
                pred_dict['strategy'],
                pred_dict['volume'],
                pred_dict['time_to_expiry_hours']
            ))
            await db.commit()
            
            prediction_id = cursor.lastrowid
            
            self.logger.info(
                f"Logged AI prediction for {market_id}",
                prediction_id=prediction_id,
                predicted_side=predicted_side,
                confidence=confidence,
                edge=edge_magnitude
            )
            
            return prediction_id
    
    async def validate_outcome(
        self,
        market_id: str,
        actual_result: str
    ) -> int:
        """
        Validate prediction outcome after market resolves.
        
        Args:
            market_id: Market identifier
            actual_result: Actual market result ("YES", "NO", or "VOID")
            
        Returns:
            Number of predictions validated
        """
        validation_time = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_manager.db_path) as db:
            # Get all unvalidated predictions for this market
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM ai_predictions 
                WHERE market_id = ? AND actual_result IS NULL
            """, (market_id,))
            
            predictions = await cursor.fetchall()
            
            if not predictions:
                self.logger.debug(f"No unvalidated predictions found for {market_id}")
                return 0
            
            # Validate each prediction
            validated_count = 0
            for pred in predictions:
                predicted_side = pred['predicted_side']
                
                # Determine correctness
                if actual_result == "VOID":
                    was_correct = None  # Don't count voided markets
                else:
                    was_correct = (predicted_side == actual_result)
                
                # Update prediction
                await db.execute("""
                    UPDATE ai_predictions 
                    SET actual_result = ?, was_correct = ?, validation_timestamp = ?
                    WHERE id = ?
                """, (actual_result, was_correct, validation_time, pred['id']))
                
                validated_count += 1
                
                self.logger.info(
                    f"Validated prediction for {market_id}",
                    predicted_side=predicted_side,
                    actual_result=actual_result,
                    was_correct=was_correct,
                    confidence=pred['confidence']
                )
            
            await db.commit()
            
            return validated_count
    
    async def get_accuracy_metrics(
        self,
        days_back: int = 7,
        strategy: Optional[str] = None,
        min_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate accuracy metrics for AI predictions.
        
        Args:
            days_back: Number of days to look back
            strategy: Filter by specific strategy (optional)
            min_confidence: Minimum confidence threshold (optional)
            
        Returns:
            Dictionary with accuracy metrics
        """
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        async with aiosqlite.connect(self.db_manager.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Build query based on filters
            query = """
                SELECT 
                    COUNT(*) as total_predictions,
                    SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct_predictions,
                    SUM(CASE WHEN was_correct = 0 THEN 1 ELSE 0 END) as incorrect_predictions,
                    SUM(CASE WHEN was_correct IS NULL THEN 1 ELSE 0 END) as pending_predictions,
                    AVG(confidence) as avg_confidence,
                    AVG(edge_magnitude) as avg_edge,
                    AVG(CASE WHEN was_correct = 1 THEN confidence ELSE 0 END) as avg_confidence_when_correct,
                    AVG(CASE WHEN was_correct = 0 THEN confidence ELSE 0 END) as avg_confidence_when_wrong
                FROM ai_predictions 
                WHERE prediction_timestamp >= ?
            """
            
            params = [cutoff_date]
            
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            
            if min_confidence:
                query += " AND confidence >= ?"
                params.append(min_confidence)
            
            cursor = await db.execute(query, params)
            result = await cursor.fetchone()
            
            if not result or result['total_predictions'] == 0:
                return {
                    'overall_accuracy': 0.0,
                    'total_predictions': 0,
                    'correct_predictions': 0,
                    'incorrect_predictions': 0,
                    'pending_predictions': 0,
                    'avg_confidence': 0.0,
                    'avg_edge': 0.0,
                    'confidence_calibration': 0.0
                }
            
            # Calculate metrics
            validated_predictions = result['correct_predictions'] + result['incorrect_predictions']
            
            accuracy = 0.0
            if validated_predictions > 0:
                accuracy = result['correct_predictions'] / validated_predictions
            
            # Confidence calibration (how well confidence predicts accuracy)
            avg_conf_correct = result['avg_confidence_when_correct'] or 0.0
            avg_conf_wrong = result['avg_confidence_when_wrong'] or 0.0
            calibration = avg_conf_correct - avg_conf_wrong
            
            metrics = {
                'overall_accuracy': accuracy,
                'total_predictions': result['total_predictions'],
                'correct_predictions': result['correct_predictions'],
                'incorrect_predictions': result['incorrect_predictions'],
                'pending_predictions': result['pending_predictions'],
                'avg_confidence': result['avg_confidence'] or 0.0,
                'avg_edge': result['avg_edge'] or 0.0,
                'confidence_calibration': calibration,
                'days_back': days_back,
                'strategy_filter': strategy,
                'min_confidence_filter': min_confidence
            }
            
            # Get accuracy by confidence bracket
            brackets = await self._get_accuracy_by_confidence_bracket(db, cutoff_date, strategy)
            metrics['accuracy_by_confidence'] = brackets
            
            # Get accuracy by strategy
            if not strategy:
                by_strategy = await self._get_accuracy_by_strategy(db, cutoff_date)
                metrics['accuracy_by_strategy'] = by_strategy
            
            return metrics
    
    async def _get_accuracy_by_confidence_bracket(
        self,
        db: aiosqlite.Connection,
        cutoff_date: str,
        strategy: Optional[str]
    ) -> Dict[str, float]:
        """Get accuracy broken down by confidence brackets."""
        brackets = {
            'low (50-65%)': (0.50, 0.65),
            'medium (65-75%)': (0.65, 0.75),
            'high (75-85%)': (0.75, 0.85),
            'very_high (85%+)': (0.85, 1.0)
        }
        
        results = {}
        
        for bracket_name, (min_conf, max_conf) in brackets.items():
            query = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct
                FROM ai_predictions 
                WHERE prediction_timestamp >= ?
                AND confidence >= ? AND confidence < ?
                AND was_correct IS NOT NULL
            """
            
            params = [cutoff_date, min_conf, max_conf]
            
            if strategy:
                query += " AND strategy = ?"
                params.append(strategy)
            
            cursor = await db.execute(query, params)
            result = await cursor.fetchone()
            
            if result and result[0] > 0:
                accuracy = result[1] / result[0]
                results[bracket_name] = {
                    'accuracy': accuracy,
                    'sample_size': result[0]
                }
            else:
                results[bracket_name] = {
                    'accuracy': 0.0,
                    'sample_size': 0
                }
        
        return results
    
    async def _get_accuracy_by_strategy(
        self,
        db: aiosqlite.Connection,
        cutoff_date: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get accuracy broken down by strategy."""
        query = """
            SELECT 
                strategy,
                COUNT(*) as total,
                SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                AVG(confidence) as avg_confidence
            FROM ai_predictions 
            WHERE prediction_timestamp >= ?
            AND was_correct IS NOT NULL
            GROUP BY strategy
        """
        
        cursor = await db.execute(query, [cutoff_date])
        results = await cursor.fetchall()
        
        by_strategy = {}
        for row in results:
            strategy = row[0]
            total = row[1]
            correct = row[2]
            avg_confidence = row[3]
            
            accuracy = correct / total if total > 0 else 0.0
            
            by_strategy[strategy] = {
                'accuracy': accuracy,
                'sample_size': total,
                'avg_confidence': avg_confidence
            }
        
        return by_strategy
    
    async def get_recent_predictions(
        self,
        limit: int = 20,
        include_pending: bool = True
    ) -> List[AIPrediction]:
        """
        Get recent predictions for review.
        
        Args:
            limit: Maximum number of predictions to return
            include_pending: Include unvalidated predictions
            
        Returns:
            List of AIPrediction objects
        """
        async with aiosqlite.connect(self.db_manager.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            query = "SELECT * FROM ai_predictions"
            
            if not include_pending:
                query += " WHERE was_correct IS NOT NULL"
            
            query += " ORDER BY prediction_timestamp DESC LIMIT ?"
            
            cursor = await db.execute(query, (limit,))
            rows = await cursor.fetchall()
            
            predictions = []
            for row in rows:
                pred_dict = dict(row)
                pred_dict['prediction_timestamp'] = datetime.fromisoformat(pred_dict['prediction_timestamp'])
                if pred_dict['validation_timestamp']:
                    pred_dict['validation_timestamp'] = datetime.fromisoformat(pred_dict['validation_timestamp'])
                
                predictions.append(AIPrediction(**pred_dict))
            
            return predictions


# Helper function for easy integration
async def create_accuracy_tracker(db_manager: DatabaseManager) -> AIAccuracyTracker:
    """
    Create and initialize an AI accuracy tracker.
    
    Args:
        db_manager: DatabaseManager instance
        
    Returns:
        Initialized AIAccuracyTracker
    """
    tracker = AIAccuracyTracker(db_manager)
    await tracker.initialize()
    return tracker
