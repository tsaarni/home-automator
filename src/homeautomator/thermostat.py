import asyncio
import datetime
import json
import logging

import aiomqtt
import task
import utils

logger = logging.getLogger("app.thermostat")


class Thermostat(object):
    def configure(self, instance_name, config):
        self.instance_name = instance_name
        self.server = config["server"]
        self.port = config.get("port", 1883)
        self.topic = config["topic"]
        self.target_temperature = config["setback"]["temperature"]
        self.effective_temperature = self.target_temperature
        self.setback_delay = utils.parse_timedelta(config["setback"]["delay"])

    async def start(self):
        logger.info(f"Starting Heater instance_name={self.instance_name}")

        while True:
            try:
                await self.loop_forever()
            except Exception as e:
                logger.exception("Error:", exc_info=e)
                await asyncio.sleep(60)

    async def loop_forever(self):
        async with aiomqtt.Client(self.server, self.port) as client:
            async with client.messages() as messages:
                await client.subscribe(self.topic)

                pending = [asyncio.create_task(anext(messages))]
                while True:
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for result in done:
                        c = result.result()
                        if isinstance(c, aiomqtt.Message):
                            payload = parse_message(c)
                            # Schedule a setback if the current temperature is different from the target temperature
                            # and timer is not already running.
                            if self.should_schedule_setback(payload["value"]) and not pending:
                                pending.add(
                                    asyncio.create_task(
                                        self.set_temperature_delayed(client, self.setback_delay.total_seconds())
                                    )
                                )
                            # Wait for the next message from the thermostat.
                            pending.add(asyncio.create_task(anext(messages)))

    def should_schedule_setback(self, current_temperature):
        if current_temperature == self.target_temperature:
            res = False
        elif current_temperature != self.effective_temperature:
            res = True
        else:
            res = False
        self.effective_temperature = current_temperature
        return res

    async def set_temperature_delayed(self, client, timeout):
        logger.debug(f"Schedule temperature to be adjusted to {self.target_temperature} in {timeout} seconds.")
        await asyncio.sleep(timeout)

        topic = self.topic + "/set"
        payload = json.dumps(
            {
                "value": self.target_temperature,
            }
        )
        logger.info(f"Publish topic={topic} payload={payload}")
        await client.publish(topic, payload)


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
