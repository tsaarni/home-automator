# Home automation server

⚠️ Note: This project is meant for personal use, and is not guaranteed to work for anyone else.

## Description

This project is a home automation server, which runs various services to control my home.

- MQTT timer: Publishes MQTT messages at a specified times of the day.
  It supports sunrise/sunset times as defined by [astral](https://astral.readthedocs.io/en/latest/) module.
  It can be used to control lights, for example.
- Thermostat controller: Controls a thermostat setpoint based on events.
  Currently, it can set the temperature to a "setback" value after specified delay.
  It is used to set default settings back after adjusting temperature manually, for example when taking a shower.

## Development

Install dependencies with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Execute the application:

```bash
python3 app/main.py --config config.yaml
```

Build the container image:

```bash
docker build -t quay.io/tsaarni/home-automator:latest .
```
