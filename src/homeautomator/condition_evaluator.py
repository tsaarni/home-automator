"""Condition evaluation for rules engine."""

import logging
import operator
from typing import Any, Dict, Optional

from homeautomator.models import Condition, ConditionsBlock
import utils

logger = logging.getLogger("app.condition_evaluator")


class ConditionEvaluator:
    """Evaluates rule conditions against current state."""

    def __init__(self, state: Dict[str, Any]):
        """Initialize the condition evaluator.

        Args:
            state: Dictionary mapping topic names to their current values.
        """
        self.state = state

    def evaluate(self, conditions_block: Optional[ConditionsBlock]) -> bool:
        """Evaluate a conditions block.

        Args:
            conditions_block: The conditions block to evaluate (can be None).

        Returns:
            True if conditions are met, False otherwise. None/empty conditions return True.
        """
        if conditions_block is None:
            return True

        # Support both 'all' (AND) and 'any' (OR) logical operators
        if conditions_block.all is not None:
            for cond in conditions_block.all:
                if not self._evaluate_single(cond):
                    return False
            return True
        elif conditions_block.any is not None:
            for cond in conditions_block.any:
                if self._evaluate_single(cond):
                    return True
            return False
        else:
            # No conditions means always true
            return True

    def _evaluate_single(self, condition: Condition) -> bool:
        """Evaluate a single condition.

        Args:
            condition: The condition to evaluate.

        Returns:
            True if condition is met, False otherwise.
        """
        current = self.state.get(condition.topic)
        if current is None:
            logger.warning(f"Condition failed: {condition.topic} is unknown")
            return False

        target = utils.parse_numeric_value(condition.value)
        return self._compare(current, condition.operator, target)

    def _compare(self, a, op: str, b) -> bool:
        """Compare two values using the specified operator.

        Args:
            a: First value.
            op: Comparison operator (gt, lt, eq, ne, ge, le).
            b: Second value.

        Returns:
            Result of the comparison.
        """
        ops = {
            "gt": operator.gt,
            "lt": operator.lt,
            "eq": operator.eq,
            "ne": operator.ne,
            "ge": operator.ge,
            "le": operator.le,
        }
        try:
            return ops.get(op, lambda x, y: False)(a, b)
        except TypeError:
            return False
