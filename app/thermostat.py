import asyncio
import datetime
import json
import logging

import aiomqtt
import task

logger = logging.getLogger("app.thermostat")


class Thermostat(object):
    def configure(self, instance_name, config):
        self.instance_name = instance_name
        self.server = config["server"]
        self.port = config.get("port", 1883)
        self.topic = config["topic"]
        self.setback_temperature = config["setback"]["temperature"]
        self.setback_delay = parse_time_interval(config["setback"]["delay"])

    async def start(self):
        logger.info(f"Starting Heater instance_name={self.instance_name}")

        while True:
            try:
                await self.loop_forever()
            except Exception as e:
                logger.exception("Error:", exc_info=e)

    async def loop_forever(self):
        async with aiomqtt.Client(self.server, self.port) as client:
            async with client.messages() as messages:
                await client.subscribe(self.topic)
                await self.adjust_temperature(messages)

    async def adjust_temperature(self, messages):
        # Temperature currently set on the thermostat.
        current_temperature = None

        # Wait for the first message from the thermostat.
        pending = [anext(messages)]

        while True:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            # Process the events.
            for task in done:
                result = task.result()

                # Check if we received MQTT message.
                if isinstance(result, aiomqtt.Message):
                    payload = parse_message(result)

                    # If the thermostat was set to target temperature, then nothing needs to be done.
                    if payload["value"] == self.setback_temperature:
                        logger.debug(
                            f"Ignore event since thermostat was already set to target temperature {payload['value']}."
                        )
                        # Cancel if there was a timeout scheduled for setback.
                        for task in pending:
                            task.cancel()

                    # If the thermostat was adjusted manually, set back the target temperature after a delay.
                    elif payload["value"] != current_temperature:
                        current_temperature = payload["value"]

                        # Cancel if there was a timeout scheduled for setback and start a new one from now.
                        for task in pending:
                            task.cancel()

                        # Schedule a timeout to set back the target temperature.
                        pending.add(asyncio.sleep(self.setback_delay.total_seconds()))

                        logger.debug(
                            f"Thermostat adjusted manually to {payload['value']}. Setback to {self.setback_temperature} in {self.setback_delay}"
                        )

                    # Wait for the next message from the thermostat.
                    pending.add(anext(messages))

                else:
                    # Publish the setback temperature to the thermostat.
                    # logger.info(f"Setting thermostat to {self.setback_temperature}")
                    topic = self.topic + "/set"
                    payload = json.dumps(
                        {
                            "value": self.setback_temperature,
                        }
                    )
                    logger.debug(f"Publish topic={topic} payload={payload}")

                    async with aiomqtt.Client(self.server, self.port) as client:
                        await client.publish(topic, payload)


def parse_time_interval(interval):
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "s":
        return datetime.timedelta(seconds=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    else:
        raise ValueError(f"Invalid unit: {unit}")


def parse_message(message):
    topic = message.topic
    payload = json.loads(message.payload)

    payload_dbg = {
        "time": datetime.datetime.fromtimestamp(payload["time"] / 1000).isoformat() if "time" in payload else None,
        "value": payload["value"] if "value" in payload else None,
    }
    logger.debug(f"Received topic={topic} payload={payload_dbg}")

    return payload


task.register(Thermostat, "thermostat")
