import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import yaml
from pydantic import ValidationError

from homeautomator.rules_engine import RulesEngine
from homeautomator.models import Rule

# Load the example rules to use in tests
RULES_FILE = os.path.join(os.path.dirname(__file__), "../rules-example.yaml")
with open(RULES_FILE, "r") as f:
    EXAMPLE_CONFIG = yaml.safe_load(f)


class TestRulesEngineScenarios(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = RulesEngine()
        # Mock the MQTT client
        self.mock_client = AsyncMock()
        self.engine.client = self.mock_client
        # Setup targets config with real mappings
        self.engine.topics = {
            "light.outdoor": ["zigbee2mqtt/light-outdoor/set"],
            "thermostat.bathroom": ["zwave/thermostat-bathroom/67/0/setpoint/1/set"],
            "thermostat.livingroom": ["zwave/thermostat-livingroom/67/0/setpoint/1/set"],
        }
        # Initialize state
        self.engine.state = {}
        # Initialize active_mqtt_triggers
        self.engine.active_mqtt_triggers = {}

    def get_rule_by_id(self, rule_id):
        """Get a rule from example config and parse it as Pydantic model."""
        for raw_rule in EXAMPLE_CONFIG["rules"]:
            if raw_rule.get("id") == rule_id:
                try:
                    return Rule(**raw_rule)
                except ValidationError as e:
                    self.fail(f"Failed to parse rule {rule_id}: {e}")
        return None

    async def trigger_topic(self, topic, rule):
        """Manually trigger evaluation of a rule."""
        # Initialize components if needed
        if not hasattr(self.engine, "condition_evaluator") or self.engine.condition_evaluator is None:
            from homeautomator.condition_evaluator import ConditionEvaluator

            self.engine.condition_evaluator = ConditionEvaluator(self.engine.state)
        if not hasattr(self.engine, "action_executor") or self.engine.action_executor is None:
            from homeautomator.action_executor import ActionExecutor

            self.engine.action_executor = ActionExecutor(self.mock_client, self.engine.topics, self.engine.state)
        await self.engine._evaluate_and_execute(rule)

    async def test_energy_limit_reduce(self):
        """
        Scenario: Reduce heating when energy consumption high
        Trigger: topic "total_energy_consumption"
        Condition: > 15000W
        Action: setpoint thermostat.livingroom = 10
        """
        rule = self.get_rule_by_id("energy_limit_reduce")
        self.assertIsNotNone(rule, "Rule 'energy_limit_reduce' not found in example config")
        assert rule is not None

        # Simulate receiving a topic update that triggers the rule
        topic = "total_energy_consumption"
        value = 16000  # > 15000
        self.engine.state[topic] = value

        # Trigger evaluation
        await self.trigger_topic(topic, rule)

        # Verify action - publish should be called with expanded MQTT topic
        self.mock_client.publish.assert_called_with(
            "zwave/thermostat-livingroom/67/0/setpoint/1/set", json.dumps({"value": 10.0})
        )

    async def test_curve_outside_temp(self):
        """
        Scenario: Heating curve based on outside temperature
        Trigger: topic "outside_temperature"
        Action: set_curve for thermostat.bathroom based on outside_temperature
        Points: [-20, 25], [-5, 23], [0, 21], [10, 19], [20, 17]
        """
        rule = self.get_rule_by_id("curve_outside_temp")
        self.assertIsNotNone(rule, "Rule 'curve_outside_temp' not found in example config")
        assert rule is not None

        # Test interpolation at 5 degrees (midpoint between 0 and 10)
        # At 0 -> 21, at 10 -> 19. Midpoint 5 should be 20.
        topic = "outside_temperature"
        value = 5
        self.engine.state[topic] = value

        await self.trigger_topic(topic, rule)

        # Verify action - publish should be called with expanded MQTT topic
        self.mock_client.publish.assert_called_with(
            "zwave/thermostat-bathroom/67/0/setpoint/1/set", json.dumps({"value": 20.0})
        )

    async def test_bathroom_manual_setback_delayed(self):
        """
        Scenario: Manual setpoint with timeout
        Trigger: thermostat.bathroom != 16
        Action: setpoint thermostat.bathroom = 16 after 4h
        """
        rule = self.get_rule_by_id("bathroom_manual_setback")
        self.assertIsNotNone(rule, "Rule 'bathroom_manual_setback' not found in example config")
        assert rule is not None

        # Trigger: thermostat.bathroom != 16
        topic = "thermostat.bathroom"
        value = 22
        self.engine.state[topic] = value

        # We mock create_task to verify the delayed action is scheduled
        with patch("asyncio.create_task") as mock_create_task:
            await self.trigger_topic(topic, rule)

            # Verify a task was created for the delayed action
            mock_create_task.assert_called_once()

            # Clean up the coroutine to avoid RuntimeWarning
            coro = mock_create_task.call_args[0][0]
            coro.close()

    async def test_price_spike_shed(self):
        """
        Scenario: Shed heating on expensive electricity
        Trigger: electricity_price
        Condition: > 0.25
        Action: setpoint thermostat.all_zones = 16
        """
        rule = self.get_rule_by_id("price_spike_shed")
        self.assertIsNotNone(rule)
        assert rule is not None

        topic = "electricity_price"
        value = 0.30  # > 0.25
        self.engine.state[topic] = value

        await self.trigger_topic(topic, rule)

        self.mock_client.publish.assert_called_with("thermostat.all_zones", json.dumps({"value": 16.0}))

    async def test_outdoor_lights_dusk(self):
        """
        Scenario: Outdoor lights on at dusk
        Trigger: time at dusk
        Action: switch light.outdoor = ON
        """
        import datetime

        rule = self.get_rule_by_id("outdoor_lights_dusk")
        self.assertIsNotNone(rule)
        assert rule is not None

        # Configure engine with location so time resolution works
        config = {
            "timezone": "UTC",
            "location": {"latitude": 51.5, "longitude": -0.1},
            "rules": [],
        }
        self.engine.configure("test_engine", config)
        # configure() resets .client to None, so we must restore the mock
        self.engine.client = self.mock_client
        # Restore topics mapping after configure
        self.engine.topics = {
            "light.outdoor": ["zigbee2mqtt/light-outdoor/set"],
        }

        # Verify time scheduler can calculate dusk
        # Use a fixed date
        date = datetime.date(2023, 1, 1)
        from homeautomator.time_scheduler import TimeScheduler

        scheduler = TimeScheduler(self.engine.city)
        dusk_time = scheduler._resolve_time("dusk", date)
        self.assertIsNotNone(dusk_time, "Should resolve dusk time with location configured")

        # Verify the action execution
        await self.trigger_topic("time", rule)

        # Verify action - publish should be called with expanded MQTT topic for zigbee2mqtt
        self.mock_client.publish.assert_called_with("zigbee2mqtt/light-outdoor/set", json.dumps({"state": "ON"}))


if __name__ == "__main__":
    unittest.main()
