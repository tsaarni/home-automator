"""Rule indexing for efficient topic-to-rule lookups."""

import logging
from typing import Dict, List, Set

from homeautomator.models import Rule, TriggerType

logger = logging.getLogger("app.rule_indexer")


class RuleIndexer:
    """Indexes rules by topic for efficient lookups."""

    def __init__(self):
        """Initialize the rule indexer."""
        self.rules: Dict[str, List[Rule]] = {}
        self.condition_rules: Dict[str, List[Rule]] = {}
        self.topics: Set[str] = set()

    def index_rules(self, rules: List[Rule]) -> None:
        """Build indexes for rules.

        Creates mappings from MQTT topics to rules.

        Args:
            rules: List of rules to index.
        """
        self.rules = {}
        self.condition_rules = {}
        self.topics = set()

        for rule in rules:
            if not rule.enabled:
                continue

            # Index MQTT-triggered rules by topic name
            if rule.trigger.type == TriggerType.MQTT and rule.trigger.name:
                name = rule.trigger.name
                self.topics.add(name)
                self.rules.setdefault(name, []).append(rule)

            # Index all topics referenced in conditions
            if rule.conditions:
                all_conditions = []
                if rule.conditions.all:
                    all_conditions.extend(rule.conditions.all)
                if rule.conditions.any:
                    all_conditions.extend(rule.conditions.any)

                for cond in all_conditions:
                    topic = cond.topic
                    self.topics.add(topic)
                    self.condition_rules.setdefault(topic, []).append(rule)

    def get_topics(self) -> Set[str]:
        """Get all topics referenced in rules.

        Returns:
            Set of MQTT topic names to subscribe to.
        """
        return self.topics

    def get_rules_for_trigger(self, topic: str) -> List[Rule]:
        """Get rules triggered by an MQTT topic.

        Args:
            topic: The MQTT topic that was updated.

        Returns:
            List of rules triggered by this topic.
        """
        return self.rules.get(topic, [])

    def get_rules_for_condition_topic(self, topic: str) -> List[Rule]:
        """Get rules that have this topic in their conditions.

        Args:
            topic: The MQTT topic that was updated.

        Returns:
            List of rules that reference this topic in conditions.
        """
        return self.condition_rules.get(topic, [])
