#!/usr/bin/env python3
"""
The MIT License

Copyright (c) 2019 Kyle Christensen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import logging
import os
import signal
import sys
import threading
from configparser import ConfigParser
from time import sleep, time

import paho.mqtt.client as mqtt_client
import requests
from crontab import CronTab


def cron_check(cron_kill):
    """ Poll until it is time to trigger a watering """
    logger.info(
        "Started thread to water on schedule (%s)", CFG["bedwetter"]["cron_schedule"]
    )
    cron = CronTab(f'{CFG["bedwetter"]["cron_schedule"]}')
    while True:
        if cron_kill():
            logger.info("Received kill signal, killing cron check thread")
            break
        time_until_cron = cron.next(default_utc=False)
        if time_until_cron < 30:
            # Sleep until it's closer to cron time to avoid a possible race
            sleep(time_until_cron)
            check_if_watering()
        else:
            # The higher this value is, the longer it takes to kill this thread
            sleep(10)


def check_if_watering():
    """ Check if we should water today, and if so water """
    logger.info("Checking if we're going to water today.")
    water = False
    if (int(time()) - int(CFG["bedwetter"]["last_water"])) > (
        86400 * int(CFG["bedwetter"]["threshold_days"])
    ):
        logger.info(
            "It has been more than %s days since last watering, time to water.",
            CFG["bedwetter"]["threshold_days"],
        )
        water = True
    else:
        if CFG["bedwetter"]["weather_api"] == "darksky":
            forecast = fetch_darksky_forecast()["daily"]["data"][0]
            if (
                "precipType" in forecast
                and (forecast["precipProbability"] * 100)
                < int(CFG["bedwetter"]["threshold_percent"])
                and forecast["precipType"] == "rain"
            ):
                logger.info(
                    "%s%% chance of %s in the next day, time to water.",
                    f'{forecast["precipProbability"] * 100:.0f}',
                    forecast["precipType"],
                )
                water = True
        elif CFG["bedwetter"]["weather_api"] == "weatherflow":
            forecast = fetch_weatherflow_conditions()
            # TODO: WeatherFlow Forecast API is forthcoming
            # For now, there's forecasting, so just check if there's < 5mm of
            # precipitation recently
            if (
                int(forecast["obs"][0]["precip_accum_local_yesterday"])
                + int(forecast["obs"][0]["precip_accum_local_day"])
                < 5
            ):
                logger.info("Less than 5mm of rain in the past day, time to water.")
                water = True

    if water:
        log_and_publish(
            "wateringStart", int(CFG["bedwetter"]["watering_duration"]), True,
        )
    else:
        log_and_publish(
            "wateringSkipped",
            "Not watering today.",
            CFG["bedwetter"].getboolean("notify_on_inaction"),
        )


def config_get_path():
    """ Return the path to the config file """
    return os.path.expanduser("~/.config/bedwetter/bedwetter.cfg")


def config_load():
    """ Load configuration options from file """
    global CFG
    config_file = config_get_path()
    CFG = ConfigParser()
    CFG.read(config_file)


def config_update():
    """ Updates the config file with any changes that have been made """
    config_file = config_get_path()

    try:
        with open(config_file, "w") as cfg_handle:
            CFG.write(cfg_handle)
    except EnvironmentError:
        log_and_publish(
            "wateringFailure",
            "Could not write to configuration file {config_file}",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def fetch_darksky_forecast():
    """ Fetch forecast information for the next day from Dark Sky """
    try:
        darksky_url = (
            "https://api.darksky.net/forecast/"
            f'{CFG["bedwetter"]["darksky_api_key"]}/'
            f'{CFG["bedwetter"]["latitude"]},'
            f'{CFG["bedwetter"]["longitude"]}'
        )
        request = requests.get(darksky_url, timeout=int(CFG["bedwetter"]["timeout"]))
        request.encoding = "utf-8"
        return request.json()
    except requests.exceptions.Timeout:
        log_and_publish(
            "wateringFailure",
            f'Error: Dark Sky API timed out after {CFG["bedwetter"]["timeout"]} seconds',
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )
    except requests.exceptions.RequestException:
        log_and_publish(
            "wateringFailure",
            "Error: There was an error connecting to the Dark Sky API",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def fetch_weatherflow_conditions():
    """ Fetch current weather information for a specified station from WeatherFlow """
    try:
        weatherflow_url = (
            "https://swd.weatherflow.com/swd/rest/observations/station/"
            f'{CFG["bedwetter"]["weatherflow_station_id"]}'
            f'?api_key={CFG["bedwetter"]["weatherflow_api_key"]}'
        )
        request = requests.get(
            weatherflow_url, timeout=int(CFG["bedwetter"]["timeout"])
        )
        request.encoding = "utf-8"
        return request.json()
    except requests.exceptions.Timeout:
        log_and_publish(
            "wateringFailure",
            f'Error: WeatherFlow API timed out after {CFG["bedwetter"]["timeout"]} seconds',
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )
    except requests.exceptions.RequestException:
        log_and_publish(
            "wateringFailure",
            "Error: There was an error connecting to the WeatherFlow API",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def log_and_publish(topic, payload, publish):
    """ Log a message to the logger, and optionally publish to mqtt """
    logger.info(payload)
    if publish:
        (rc, _) = client.publish(
            f'{CFG["bedwetter"]["mqtt_topic"]}/event/{topic}',
            payload=payload,
            qos=1,
            retain=False,
        )
        if rc != 0:
            logger.error("Unable to publish mqtt message, rc is %s", rc)


def on_connect(client, userdata, flags, rc):
    """ Connect to mqtt broker and subscribe to the bedwetter topic """
    logger.info("Connected to the mqtt broker")
    client.subscribe(f'{CFG["bedwetter"]["mqtt_topic"]}/#')
    if "cron_schedule" in CFG["bedwetter"] and CFG["bedwetter"]["cron_schedule"]:
        global cron_kill
        global cron_thread
        cron_kill = False
        cron_thread = threading.Thread(target=cron_check, args=(lambda: cron_kill,))
        cron_thread.daemon = True
        cron_thread.start()
        if not cron_thread.is_alive():
            logger.error("Unable to start cron check process")
    else:
        logger.info("Not starting cron check thread, cron time string is not set")


def on_disconnect(client, userdata, rc):
    """ Log when disconnected from the mqtt broker """
    logger.info("Disconnected from the mqtt broker")
    # Kill cron_thread if it is running, otherwise we'll end up with
    # a new one on every reconnection to the mqtt broker
    if cron_thread.is_alive():
        logger.info("Trying to kill cron check, this can take a few seconds")
        global cron_kill
        cron_kill = True
        cron_thread.join()


def on_message(client, userdata, msg):
    """ On receipt of a message, do stuff """
    if "wateringStart" in msg.topic:
        logger.info("Received wateringStart mqtt message")
        if not msg.payload:
            duration = int(CFG["bedwetter"]["watering_duration"])
        else:
            duration = int(msg.payload)
        if not water_on(duration):
            log_and_publish(
                "wateringFailure",
                "Watering failed to start.",
                CFG["bedwetter"].getboolean("notify_on_failure"),
            )
        else:
            log_and_publish(
                "wateringSuccess",
                "Watering was successful.",
                CFG["bedwetter"].getboolean("notify_on_success"),
            )
    elif "wateringStop" in msg.topic:
        logger.info("Received wateringStop mqtt message")
        if not water_off():
            log_and_publish(
                "wateringRunaway",
                "Watering failed to stop!",
                CFG["bedwetter"].getboolean("notify_on_failure"),
            )


def setup_logger():
    """ Setup logging to file and stdout """
    # Setup date formatting
    formatter = logging.Formatter(
        "%(asctime)-15s %(levelname)s - %(message)s", datefmt="%b %d %H:%M:%S"
    )

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Log to stdout
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Optionally log to file
    if "log_file" in CFG["bedwetter"] and CFG["bedwetter"].getboolean("log_to_file"):
        file_handler = logging.FileHandler(
            os.path.expanduser(CFG["bedwetter"]["log_file"])
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def shutdown(_signo, _stack_frame):
    log_and_publish("shuttingDown", "Caught SIGTERM, shutting down", True)
    sys.exit(0)


def water_on(duration):
    """ Start watering """
    logger.info("Watering for %s seconds", duration)
    try:
        automationhat.relay.one.on()
        if automationhat.relay.one.is_on():
            sleep(duration)
            CFG["bedwetter"]["last_water"] = f"{time():.0f}"
            config_update()
            return True
    except NameError as name_e:
        logger.info(name_e)
    return False


def water_off():
    """ Stop watering """
    logger.info("Turning water off")
    try:
        automationhat.relay.one.off()
        if automationhat.relay.one.is_off():
            return True
    except NameError as name_e:
        logger.info(name_e)
    return False


def main():
    """ Main """
    # Load config file settings
    config_load()

    # Setup logger
    global logger
    logger = setup_logger()

    # Try importing automationhat if it exists
    try:
        import automationhat
    except ImportError:
        logger.warning("Unable to import automationhat, continuing in development mode")

    # Catch SIGTERM when being run via Systemd
    signal.signal(signal.SIGTERM, shutdown)

    global client
    client = mqtt_client.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.tls_set(ca_certs=f"{os.path.dirname(__file__)}/ssl/letsencrypt-root.pem")
    client.username_pw_set(
        CFG["bedwetter"]["mqtt_username"], CFG["bedwetter"]["mqtt_password"],
    )

    try:
        client.connect(
            CFG["bedwetter"]["mqtt_server"],
            port=CFG["bedwetter"].getint("mqtt_port"),
            keepalive=60,
        )
    # Paho swallows exceptions so I doubt this even works
    except Exception as paho_e:
        logger.info("Unable to connect to mqtt broker, %s", paho_e)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down")
        client.disconnect()
        sys.exit(0)


if sys.version_info >= (3, 7):
    if __name__ == "__main__":
        main()
else:
    sys.exit("Fatal Error: This script requires Python 3.7 or greater")
