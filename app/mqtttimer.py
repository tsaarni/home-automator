import datetime
import logging
from typing import Dict, List

import aiomqtt
import astral
import astral.sun
import task
import utils

logger = logging.getLogger("app.mqtt-timer")


class MqttTimer(object):
    def configure(self, instance_name, config):
        self.instance_name = instance_name
        self.server = config["server"]
        self.topic = config["topic"]
        self.schedule: List[Dict[str, str]] = config["schedule"]

        # Location is optional.
        # If not specified, sunrise/sunset times will not be supported.
        if "location" in config:
            self.city = astral.LocationInfo(
                timezone=config["timezone"],
                latitude=config["location"]["latitude"],
                longitude=config["location"]["longitude"],
            )

        # Test if the schedule is valid by parsing it once before task is running.
        # Since the service may run for a long time, it needs to be parsed again later
        # to resolve sunrise/sunset times at every use.
        self.resolve_schedule()

    def resolve_schedule(self):
        # Convert configured times into datetime.time.
        resolved = []
        for entry in self.schedule:
            time = entry["time"]
            try:
                # First attempt to parse the string as HH:MM.
                resolved_time = datetime.datetime.strptime(time, "%H:%M").time()
            except ValueError:
                # If it did not succeed then attempt to resolve sunrise/sunset times into local time.
                s = astral.sun.sun(self.city.observer, date=datetime.datetime.now().date(), tzinfo=self.city.timezone)
                resolved_time = s[time].time()

            resolved.append(
                {
                    "time": resolved_time,
                    "payload": entry["payload"],
                }
            )

        # Sort the schedule by time.
        resolved.sort(key=lambda x: x["time"])

        logger.debug(f"Resolved schedule: {resolved}")
        return resolved

    # Find the schedule entry that is effective for the given time.
    def get_effective_schedule_entry(self, now, schedule):
        for idx, entry in enumerate(schedule):
            if now < entry["time"]:
                return schedule[idx - 1]
        return schedule[-1]

    async def start(self):
        logger.info(f"Starting MqttTimer instance_name={self.instance_name}")
        while True:
            schedule = self.resolve_schedule()
            try:
                await self.set_state(schedule)
            except Exception as e:
                logger.exception("Error:", exc_info=e)

            # Schedule next event.
            await utils.wait_until([dt["time"] for dt in schedule])

    async def set_state(self, schedule):
        now = datetime.datetime.now().time()
        effective_schedule = self.get_effective_schedule_entry(now, schedule)

        # Publish the state to the MQTT broker.
        logger.info(f"Publish topic={self.topic} payload={effective_schedule['payload']}")
        async with aiomqtt.Client(hostname=self.server) as mqtt_client:
            await mqtt_client.publish(self.topic, effective_schedule["payload"])


task.register(MqttTimer, "mqtt-timer")
