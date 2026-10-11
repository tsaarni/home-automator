"""Action execution for rules engine."""

import asyncio
import json
import logging
from typing import Any, Dict, List

import aiomqtt

from homeautomator.models import Action, ActionType
import utils

logger = logging.getLogger("app.action_executor")


class ActionExecutor:
    """Executes actions for rules engine."""

    def __init__(self, client: aiomqtt.Client, targets: Dict[str, Any], state: Dict[str, Any]):
        """Initialize the action executor.

        Args:
            client: MQTT client for publishing messages.
            targets: Dictionary mapping target names to MQTT topics.
            state: Current state dictionary for resolving values.
        """
        self.client = client
        self.targets = targets
        self.state = state

    async def execute_actions(self, actions: List[Action]) -> None:
        """Execute a list of actions.

        Args:
            actions: List of actions to execute.
        """
        for action in actions:
            if action.execute_after is not None:
                # Schedule delayed action
                delay = action.execute_after.total_seconds()
                asyncio.create_task(self._execute_delayed_action(action, delay))
            else:
                await self._perform_action(action)

    async def _execute_delayed_action(self, action: Action, delay: float) -> None:
        """Execute an action after a delay.

        Args:
            action: The action to execute.
            delay: Delay in seconds before execution.
        """
        logger.info(f"Scheduling action {action.type} in {delay} seconds")
        await asyncio.sleep(delay)
        await self._perform_action(action)

    async def _perform_action(self, action: Action) -> None:
        """Perform a single action.

        Args:
            action: The action to perform.
        """
        if not self.client:
            return

        await self._publish(action)

    def _calculate_curve_payload(self, action: Action, device_type: str) -> dict | None:
        """Calculate payload for a set_curve action.

        Args:
            action: The set_curve action with curve definition.
            device_type: Device type ('zwave' or 'zigbee').

        Returns:
            Payload dict with interpolated value, or None if target unknown.
        """
        if action.curve is None:
            return None

        target = action.curve.x
        val = self.state.get(target)
        if val is None:
            logger.warning(f"Cannot execute set_curve: target {target} unknown")
            return None

        interpolated_value = utils.interpolate_curve(val, action.curve.points)

        if device_type == "zigbee":
            return {"state": interpolated_value}
        else:  # zwave or unknown, default to value
            return {"value": interpolated_value}

    def _detect_device_type(self, topics: List[str]) -> str:
        """Detect device type from MQTT topic path.

        Args:
            topics: List of MQTT topic paths.

        Returns:
            Device type: 'zwave', 'zigbee', or 'unknown'.
        """
        for topic in topics:
            if "zwave" in topic.lower():
                return "zwave"
            elif "zigbee" in topic.lower():
                return "zigbee"
        return "unknown"

    def _create_payload(self, action: Action, device_type: str) -> dict | None:
        """Create payload for an action based on device type.

        Args:
            action: The action to create payload for.
            device_type: Device type ('zwave' or 'zigbee').

        Returns:
            Payload dict or None if action cannot be executed.
        """
        if action.type == ActionType.SETPOINT:
            return self._create_setpoint_payload(action.value, device_type)
        elif action.type == ActionType.SWITCH:
            return self._create_switch_payload(action.state, device_type)
        elif action.type == ActionType.SET_CURVE:
            return self._calculate_curve_payload(action, device_type)
        return None

    def _create_setpoint_payload(self, value: float | None, device_type: str) -> dict | None:
        """Create setpoint payload based on device type.

        Args:
            value: The setpoint value.
            device_type: Device type ('zwave' or 'zigbee').

        Returns:
            Payload dict appropriate for device type, or None if value is None.
        """
        if value is None:
            return None
        if device_type == "zigbee":
            return {"state": value}
        else:  # zwave or unknown, default to value
            return {"value": value}

    def _create_switch_payload(self, state: str | None, device_type: str) -> dict | None:
        """Create switch payload based on device type.

        Args:
            state: The switch state ('ON' or 'OFF').
            device_type: Device type ('zwave' or 'zigbee').

        Returns:
            Payload dict appropriate for device type, or None if state is None.
        """
        if state is None:
            return None
        if device_type == "zigbee":
            return {"state": state}
        else:  # zwave or unknown, default to value
            return {"value": state}

    async def _publish(self, action: Action) -> None:
        """Publish an action to MQTT target(s).

        Args:
            action: The action to publish.
        """
        # Expand target to actual MQTT topics
        topics = self.targets.get(action.target, [action.target])
        if isinstance(topics, str):
            topics = [topics]

        # Create and publish payload for each topic
        for topic in topics:
            device_type = self._detect_device_type([topic])
            payload = self._create_payload(action, device_type)

            if payload:
                msg = json.dumps(payload)
                await self.client.publish(topic, msg)
                logger.debug(f"Published to {topic}: {msg}")
