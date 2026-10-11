#!/usr/bin/env python3
#
# . .venv/bin/activate
# kubectl port-forward deployments/mosquitto 1883
# ./test-set-thermostat.py 20

import asyncio
import json
import sys

import aiomqtt

# zwave thermostat mqtt endpoints:
#
# Z-TRM2fx endpoints:
# 67/1/setpoint/1 - heating

# TF016 / TF021 endpoints:


endpoints = [
    "zwave/thermostat-bathroom/67/0/setpoint/1/set",
    "zwave/thermostat-livingroom/67/0/setpoint/1/set",
    "zwave/thermostat-kitchen/67/0/setpoint/1/set",
    "zwave/thermostat-hall/67/1/setpoint/1/set",
    "zwave/thermostat-toilet/67/1/setpoint/1/set",
    "zwave/thermostat-office/67/1/setpoint/1/set",
    # "zwave/thermostat-bedroom/67/1/setpoint/1/set",
    # "zwave/thermostat-emptyroom/67/1/setpoint/1/set"
]


async def main():
    target_temperature = sys.argv[1]
    async with aiomqtt.Client(hostname="localhost") as mqtt_client:
        for endpoint in endpoints:
            payload = json.dumps(
                {
                    "value": target_temperature,
                }
            )
            print(f"Sending {endpoint} payload {payload}")
            await mqtt_client.publish(endpoint, payload=payload)


if __name__ == "__main__":
    asyncio.run(main())
