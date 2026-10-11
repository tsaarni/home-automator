import unittest

from homeautomator.models import Rule, Trigger, TriggerType, Action, ActionType, Condition, ConditionsBlock
from homeautomator.condition_evaluator import ConditionEvaluator
from homeautomator.rule_indexer import RuleIndexer


class TestRulesEngineLogic(unittest.TestCase):
    def test_get_topics(self):
        """Test that topics are correctly indexed from MQTT trigger rules."""
        indexer = RuleIndexer()
        rules = [
            Rule(
                id="rule1",
                name="Test Rule 1",
                trigger=Trigger(type=TriggerType.MQTT, name="sensor1"),
                actions=[Action(type=ActionType.SETPOINT, target="test", value=20)],
            ),
            Rule(
                id="rule2",
                name="Test Rule 2",
                trigger=Trigger(type=TriggerType.MQTT, name="sensor2"),
                actions=[Action(type=ActionType.SETPOINT, target="test", value=21)],
            ),
        ]
        indexer.index_rules(rules)
        topics = indexer.get_topics()
        self.assertIn("sensor1", topics)
        self.assertIn("sensor2", topics)

    def test_evaluate_conditions(self):
        """Test condition evaluation with 'all' operator."""
        state = {"sensor1": 20}
        evaluator = ConditionEvaluator(state)

        # Condition that should pass
        conditions = ConditionsBlock(all=[Condition(topic="sensor1", operator="gt", value=10)])
        self.assertTrue(evaluator.evaluate(conditions))

        # Condition that should fail
        conditions_fail = ConditionsBlock(all=[Condition(topic="sensor1", operator="gt", value=25)])
        self.assertFalse(evaluator.evaluate(conditions_fail))

    def test_evaluate_conditions_any_operator(self):
        """Test condition evaluation with 'any' operator."""
        state = {"sensor1": 20, "sensor2": 5}
        evaluator = ConditionEvaluator(state)

        # Test 'any' operator - at least one condition must be true
        conditions = ConditionsBlock(
            any=[
                Condition(topic="sensor1", operator="gt", value=25),  # False
                Condition(topic="sensor2", operator="lt", value=10),  # True
            ]
        )
        self.assertTrue(evaluator.evaluate(conditions))

        # All conditions false
        conditions_fail = ConditionsBlock(
            any=[
                Condition(topic="sensor1", operator="gt", value=25),  # False
                Condition(topic="sensor2", operator="gt", value=10),  # False
            ]
        )
        self.assertFalse(evaluator.evaluate(conditions_fail))


if __name__ == "__main__":
    unittest.main()
