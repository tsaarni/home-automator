import datetime
from homeautomator.mqtttimer import MqttTimer


def test_schedule():
    config = {
        "schedule": [
            {
                "time": "dusk",
                "payload": "on",
            },
            {
                "time": "23:30",
                "payload": "off",
            },
            {
                "time": "6:00",
                "payload": "on",
            },
            {
                "time": "sunrise",
                "payload": "off",
            },
        ],
        "location": {
            "latitude": 60.192059,
            "longitude": 24.945831,
        },
        "timezone": "Europe/Helsinki",
        "server": "mqtt://localhost",
        "topic": "test",
    }

    timer = MqttTimer()
    timer.configure("", config)

    assert resolve(timer, datetime.time(12, 0)) == "off"
    assert resolve(timer, datetime.time(23, 0)) == "on"
    assert resolve(timer, datetime.time(23, 30)) == "off"
    assert resolve(timer, datetime.time(1, 30)) == "off"
    assert resolve(timer, datetime.time(6, 30)) == "on"
    assert resolve(timer, datetime.time(9, 30)) == "off"


def resolve(timer, time):
    return timer.get_effective_schedule_entry(time, timer.resolve_schedule())["payload"]
