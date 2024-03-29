
# Bedwetter

## About

I wrote this code to automate watering of my raised beds from a rain barrel using a
Raspberry Pi Zero W, and a [Pimoroni Automation pHAT](https://shop.pimoroni.com/products/automation-phat).

When run via systemd, it will daemonize and listen to an MQTT topic for events. Additionally, a cron-like
schedule can be set to trigger automatic watering.

When it determines it should water the gardens (based on time since last water, or the weather forecast from my [Tempest Weather System](https://weatherflow.com/tempest-weather-system/)),
it activates the relay on the Automation Phat board, which triggers a relay attached to the rain barrel
that runs an RV water pump for a predetermined amount of time.

Additionally, I have it integrated with [Home Assistant](https://www.home-assistant.io/) and [Node-Red](https://nodered.org/), so the MQTT messages it emits it will send
me push notifications, and can handle Siri shortcuts to water, skip the next automated watering, or stop watering.

## Configuration

The Automation pHAT requires that I2C be enabled on the Raspberry Pi, which can be done in `raspi-config`
under the `Interfacing Options` section.

Bedwetter is configured via a config file that should reside at `${HOME}/.config/bedwetter/bedwetter.cfg`
and contains something along the lines of:

```ini
[bedwetter]
debug = false
log_file = /var/log/bedwetter.log
log_to_file = true
mqtt_hostname = <Hostname of your mqtt server>
mqtt_password = <Your mqtt broker password>
mqtt_port = 8883
mqtt_topic = bedwetter
mqtt_username = <Your mqtt broker username>
notify_on_failure = true
notify_on_inaction = true
notify_on_service = true
notify_on_success = true
schedule = 0 8 * * *
station_id = <Your Tempest station id>
threshold_days = 2
threshold_percent = 50
timeout = 5
water_duration = 600
weatherflow_api_key = <Your WeatherFlow API key>
```

It should be noted that this project is a bit rough around the edges as I didn't really
intend to distribute it, but I thought people might be interested in it.

## Installation

Bedwetter makes use of pip and virtualenv, so install those via your system's package manager first. Then it's just a matter of running `make install` in the root of this project.
