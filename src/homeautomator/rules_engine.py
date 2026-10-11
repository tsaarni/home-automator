import asyncio
import datetime
import logging
import os
from typing import Any, Dict, List

import aiomqtt
import astral
import yaml
from pydantic import ValidationError

import task
import utils
from homeautomator.action_executor import ActionExecutor
from homeautomator.condition_evaluator import ConditionEvaluator
from homeautomator.models import Rule, TriggerType
from homeautomator.rule_indexer import RuleIndexer
from homeautomator.time_scheduler import TimeScheduler

logger = logging.getLogger("app.rules_engine")


class RulesEngine:
    def configure(self, instance_name: str, config: dict) -> None:
        self.instance_name = instance_name
        self.config = config
        self.mqtt_config = config.get("mqtt", {})
        self.topics = self.mqtt_config.get("topics", {})
        self.rules_file = config.get("rules_file")
        self.reset_interval = utils.parse_timedelta(config.get("reset_interval", "10m"))

        self.city = None
        if "location" in config:
            self.city = astral.LocationInfo(
                timezone=config["timezone"],
                latitude=config["location"]["latitude"],
                longitude=config["location"]["longitude"],
            )

        self.state: Dict[str, Any] = {}
        self.client: aiomqtt.Client
        self.recalc_schedule_event = asyncio.Event()
        self.active_mqtt_triggers: Dict[str, datetime.datetime] = {}

        # Initialize components
        self.rule_indexer = RuleIndexer()
        self.time_scheduler = TimeScheduler(self.city)
        self.condition_evaluator = None  # Created after loading rules
        self.action_executor = None  # Created after MQTT client is ready

        self._load_rules()

    def _load_rules(self) -> None:
        """Load and parse rules from file or config."""
        self.rules: List[Rule] = []
        raw_rules = []

        if self.rules_file:
            try:
                with open(self.rules_file, "r") as f:
                    raw_rules = yaml.safe_load(f).get("rules", [])
            except Exception as e:
                logger.error(f"Failed to load rules file {self.rules_file}: {e}")
        else:
            raw_rules = self.config.get("rules", [])

        # Parse rules with Pydantic validation
        for raw_rule in raw_rules:
            try:
                rule = Rule(**raw_rule)
                self.rules.append(rule)
            except ValidationError as e:
                rule_id = raw_rule.get("id", raw_rule.get("name", "unknown"))
                logger.warning(f"Skipping invalid rule '{rule_id}': {e.error_count()} validation error(s)")
                for error in e.errors():
                    logger.warning(f"  - {error['loc']}: {error['msg']}")

        logger.info(f"Loaded {len(self.rules)} valid rules")

        # Index rules for efficient lookup
        self.rule_indexer.index_rules(self.rules)

        # Create condition evaluator with current state
        self.condition_evaluator = ConditionEvaluator(self.state)

    async def start(self) -> None:
        logger.info(f"Starting RulesEngine {self.instance_name}")
        server = self.mqtt_config.get("server", "localhost")
        port = self.mqtt_config.get("port", 1883)

        async with aiomqtt.Client(server, port) as client:
            self.client = client

            # Initialize action executor now that we have MQTT client
            self.action_executor = ActionExecutor(client, self.topics, self.state)

            # Subscribe to all topics referenced in rules
            for topic in self.rule_indexer.get_topics():
                logger.info(f"Subscribing to {topic}")
                await client.subscribe(topic)

            await asyncio.gather(
                self._mqtt_loop(),
                self._time_trigger_loop(),
                self._watch_rules_file(),
                self._periodic_reeval_loop(),
            )

    async def _mqtt_loop(self) -> None:
        """Process MQTT messages and trigger rules."""
        async for message in self.client.messages:
            topic = message.topic.value
            payload = message.payload.decode()

            try:
                value = utils.parse_numeric_value(payload)
            except ValueError:
                value = payload

            logger.debug(f"Received {topic}: {value}")
            self.state[topic] = value

            # Evaluate rules triggered by this topic
            for rule in self.rule_indexer.get_rules_for_trigger(topic):
                await self._evaluate_and_execute(rule)

            # Re-evaluate rules that have this topic in their conditions
            for rule in self.rule_indexer.get_rules_for_condition_topic(topic):
                await self._evaluate_and_execute(rule)

    async def _time_trigger_loop(self) -> None:
        """Handle time-based rule triggering."""
        while True:
            schedule = self.time_scheduler.get_todays_schedule(self.rules)

            if not schedule:
                if await self._wait_for_reload(3600):
                    continue
                continue

            delay_td, next_dt = utils.next_wakeup(schedule)
            seconds = delay_td.total_seconds()
            logger.info(f"Next scheduled rule execution at {next_dt} (in {seconds}s)")

            if await self._wait_for_reload(seconds):
                continue

            # Check which time rules should trigger now
            now = datetime.datetime.now()
            matching_rules = self.time_scheduler.check_time_rules(self.rules, now)
            for rule in matching_rules:
                await self._evaluate_and_execute(rule)

            # Sleep to avoid double execution within the same minute
            await asyncio.sleep(61)

    async def _wait_for_reload(self, timeout: float) -> bool:
        """Wait for reload event with timeout.

        Args:
            timeout: Timeout in seconds.

        Returns:
            True if reload was triggered, False if timeout.
        """
        try:
            await asyncio.wait_for(self.recalc_schedule_event.wait(), timeout=timeout)
            self.recalc_schedule_event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    async def _evaluate_and_execute(self, rule: Rule, is_periodic: bool = False) -> None:
        """Evaluate rule conditions and execute actions if met.

        Args:
            rule: The rule to evaluate.
            is_periodic: Whether this is a periodic re-evaluation.
        """
        rule_id = rule.id
        logger.info(f"Evaluating rule: {rule.name}")

        assert self.condition_evaluator is not None
        if self.condition_evaluator.evaluate(rule.conditions):
            logger.info(f"Conditions met for rule: {rule.name}")

            # Track active mqtt triggers for periodic re-evaluation
            if rule.trigger.type == TriggerType.MQTT and not is_periodic:
                self.active_mqtt_triggers[rule_id] = datetime.datetime.now()

            assert self.action_executor is not None
            await self.action_executor.execute_actions(rule.actions)
        else:
            # Conditions no longer met, remove from active triggers
            if rule_id in self.active_mqtt_triggers:
                logger.debug(f"Conditions no longer met for rule: {rule.name}, removing from active triggers")
                del self.active_mqtt_triggers[rule_id]

    async def _periodic_reeval_loop(self) -> None:
        """Periodically re-evaluate active MQTT triggers while conditions hold true."""
        while True:
            await asyncio.sleep(self.reset_interval.total_seconds())

            if not self.active_mqtt_triggers:
                continue

            logger.debug(f"Periodic re-evaluation: {len(self.active_mqtt_triggers)} active triggers")

            # Create a copy to iterate over since we might modify the dict
            active_triggers = list(self.active_mqtt_triggers.items())

            for rule_id, last_exec_time in active_triggers:
                # Find the rule by id
                rule = None
                for r in self.rules:
                    if r.id == rule_id:
                        rule = r
                        break

                if rule and rule.enabled:
                    time_since_last = datetime.datetime.now() - last_exec_time
                    if time_since_last >= self.reset_interval:
                        logger.debug(f"Re-evaluating rule: {rule.name}")
                        await self._evaluate_and_execute(rule, is_periodic=True)
                        # Update last execution time if conditions still met
                        if rule_id in self.active_mqtt_triggers:
                            self.active_mqtt_triggers[rule_id] = datetime.datetime.now()

    async def _watch_rules_file(self) -> None:
        """Watch rules file for changes and reload."""
        if not self.rules_file:
            return
        last_mtime = 0
        try:
            last_mtime = os.stat(self.rules_file).st_mtime
        except FileNotFoundError:
            pass

        while True:
            await asyncio.sleep(5)
            try:
                mtime = os.stat(self.rules_file).st_mtime
                if mtime != last_mtime:
                    logger.info(f"Rules file changed, reloading...")
                    last_mtime = mtime
                    await self._reload_rules()
            except Exception as e:
                logger.error(f"Error watching rules file: {e}")

    async def _reload_rules(self) -> None:
        """Reload rules and update MQTT subscriptions."""
        try:
            old_topics = self.rule_indexer.get_topics()
            self._load_rules()
            new_topics = self.rule_indexer.get_topics()

            # Update MQTT subscriptions
            if self.client:
                for t in new_topics - old_topics:
                    logger.info(f"Subscribing to new topic {t}")
                    await self.client.subscribe(t)
                for t in old_topics - new_topics:
                    logger.info(f"Unsubscribing from topic {t}")
                    await self.client.unsubscribe(t)

            logger.info(f"Reloaded {len(self.rules)} rules")
            self.recalc_schedule_event.set()

        except Exception as e:
            logger.error(f"Failed to reload rules: {e}")


task.register(RulesEngine, "rules_engine")
