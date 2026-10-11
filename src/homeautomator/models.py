"""Pydantic models for rules engine schema validation."""

import datetime
import re
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

import utils


class TriggerType(str, Enum):
    """Types of rule triggers."""

    TIME = "time"
    MQTT = "mqtt"


class ActionType(str, Enum):
    """Types of actions that can be executed."""

    SETPOINT = "setpoint"
    SWITCH = "switch"
    SET_CURVE = "set_curve"


class TimeSchedule(BaseModel):
    """Schedule for time-based triggers."""

    model_config = ConfigDict(extra="forbid")

    at: str  # "14:30", "sunrise", "sunset", "dusk", etc.
    days: Optional[List[str]] = None  # ["Mon", "Tue", ...] or None for all days


class Trigger(BaseModel):
    """Rule trigger definition."""

    model_config = ConfigDict(extra="forbid")

    type: TriggerType
    schedule: Optional[TimeSchedule] = None  # Required for time triggers
    name: Optional[str] = None  # Required for mqtt triggers (topic name)

    @model_validator(mode="after")
    def validate_trigger_fields(self) -> "Trigger":
        """Validate that required fields are present based on trigger type."""
        if self.type == TriggerType.TIME and self.schedule is None:
            raise ValueError("Time trigger requires 'schedule' field")
        if self.type == TriggerType.MQTT and self.name is None:
            raise ValueError("MQTT trigger requires 'name' field")
        return self


class CurveDefinition(BaseModel):
    """Curve definition for set_curve actions."""

    model_config = ConfigDict(extra="forbid")

    x: str  # topic name for x values
    points: List[List[float]]  # [[x1, y1], [x2, y2], ...]

    @field_validator("points")
    @classmethod
    def validate_points(cls, v: List[List[float]]) -> List[List[float]]:
        """Validate that curve has at least 2 points."""
        if len(v) < 2:
            raise ValueError("Curve must have at least 2 points")
        for point in v:
            if len(point) != 2:
                raise ValueError("Each curve point must have exactly 2 values [x, y]")
        return v


class Action(BaseModel):
    """Action to execute when rule conditions are met."""

    model_config = ConfigDict(extra="forbid")

    type: ActionType
    target: str
    value: Optional[float] = None  # For setpoint actions
    state: Optional[str] = None  # For switch actions ("ON"/"OFF")
    curve: Optional[CurveDefinition] = None  # For set_curve actions
    execute_after: Optional[datetime.timedelta] = None  # Delay before execution

    @field_validator("execute_after", mode="before")
    @classmethod
    def parse_execute_after(cls, v: Any) -> Optional[datetime.timedelta]:
        """Convert duration string to timedelta."""
        if v is None:
            return None
        if isinstance(v, datetime.timedelta):
            return v
        if isinstance(v, str):
            return utils.parse_timedelta(v)
        raise ValueError(f"Invalid execute_after format: {v}")

    @model_validator(mode="after")
    def validate_action_fields(self) -> "Action":
        """Validate that required fields are present based on action type."""
        if self.type == ActionType.SETPOINT and self.value is None:
            raise ValueError("Setpoint action requires 'value' field")
        if self.type == ActionType.SWITCH and self.state is None:
            raise ValueError("Switch action requires 'state' field")
        if self.type == ActionType.SET_CURVE and self.curve is None:
            raise ValueError("Set_curve action requires 'curve' field")
        return self


class Condition(BaseModel):
    """Condition for rule evaluation."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    operator: Literal["gt", "lt", "eq", "ne", "ge", "le"]
    value: float | str


class ConditionsBlock(BaseModel):
    """Logical combination of conditions."""

    model_config = ConfigDict(extra="forbid")

    all: Optional[List[Condition]] = None  # AND logic
    any: Optional[List[Condition]] = None  # OR logic


class Rule(BaseModel):
    """Complete rule definition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    trigger: Trigger
    actions: List[Action]
    priority: int = 100
    enabled: bool = True
    conditions: Optional[ConditionsBlock] = None
    metadata: dict = {}

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: List[Action]) -> List[Action]:
        """Validate that at least one action exists."""
        if len(v) == 0:
            raise ValueError("Rule must have at least one action")
        return v
