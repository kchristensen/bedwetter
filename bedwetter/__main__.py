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
from time import sleep, strftime, time

import paho.mqtt.client as mqtt_client
import requests
from crontab import CronTab

# Setup some global variables because I'm lazy
CFG = None
CRON_KILL = None
CRON_SKIP = None
CRON_THREAD = None
LOGGER = None


def cb_on_connect(client, userdata, flags, rc):
    """ Connect to mqtt broker and subscribe to the bedwetter topic """
    LOGGER.info("Connected to the mqtt broker")
    client.subscribe(f'{CFG["bedwetter"]["mqtt_topic"]}/#')
    if "cron_schedule" in CFG["bedwetter"] and CFG["bedwetter"]["cron_schedule"]:
        global CRON_KILL
        global CRON_THREAD
        CRON_KILL = False
        set_cron_skip(False)
        CRON_THREAD = threading.Thread(
            target=cron_check, args=(lambda: CRON_KILL, lambda: CRON_SKIP,)
        )
        CRON_THREAD.daemon = True
        CRON_THREAD.start()
        if not CRON_THREAD.is_alive():
            LOGGER.error("Unable to start cron check process")
    else:
        LOGGER.info("Not starting cron check thread, cron time string is not set")


def cb_on_disconnect(client, userdata, rc):
    """ Log when disconnected from the mqtt broker """
    LOGGER.info("Disconnected from the mqtt broker")
    # Kill CRON_THREAD if it is running, otherwise we'll end up with
    # a new one on every reconnection to the mqtt broker
    try:
        if CRON_THREAD.is_alive():
            LOGGER.info("Trying to kill cron check, this can take a few seconds")
            global CRON_KILL
            CRON_KILL = True
            CRON_THREAD.join()
    except NameError:
        pass


def cb_on_log(client, userdata, level, buf):
    """ Log Paho debug information """
    if CFG["bedwetter"].getboolean("debug"):
        LOGGER.debug(buf)


def cb_on_message(client, userdata, msg):
    """ On receipt of a message, do stuff """
    if "wateringStart" in msg.topic:
        LOGGER.info("Received wateringStart mqtt message")
        if not msg.payload:
            duration = CFG["bedwetter"].getint("watering_duration")
        else:
            duration = int(msg.payload)
        water_on(client, duration)
        water_off(client)
    elif "wateringSkip" in msg.topic:
        if CRON_THREAD.is_alive():
            LOGGER.info("Skipping the next automatic watering")
            set_cron_skip(True)
    elif "wateringStop" in msg.topic:
        # This won't actually interrupt water_on() which blocks the read loop
        LOGGER.info("Received wateringStop mqtt message")
        water_off(client)


def check_if_watering(client):
    """ Check if we should water today, and if so water """
    LOGGER.info("Checking if we're going to water today.")
    water = False
    if (int(time()) - int(CFG["bedwetter"]["last_water"])) > (
        86400 * int(CFG["bedwetter"]["threshold_days"])
    ):
        LOGGER.info(
            "More than %s days since last watering, time to water",
            CFG["bedwetter"]["threshold_days"],
        )
        water = True
    else:
        forecast = fetch_forecast(client)["forecast"]["daily"]
        for day in forecast:
            if day["day_num"] == int(strftime("%d")) and day[
                "precip_probability"
            ] < CFG["bedwetter"].getint("threshold_percent"):
                LOGGER.info(
                    "%s%% chance of precipitation in the next day, time to water",
                    f'{day["precip_probability"]:.0f}',
                )
                water = True
    if water:
        publish(
            client, "wateringStart", CFG["bedwetter"].getint("water_duration"),
        )
    else:
        log_and_publish(
            client,
            "wateringSkipped",
            "Not watering today",
            CFG["bedwetter"].getboolean("notify_on_inaction"),
        )


def config_load():
    """ Load configuration options from file """
    global CFG
    config_file = os.path.expanduser("~/.config/bedwetter/bedwetter.cfg")
    CFG = ConfigParser()
    CFG.read(config_file)
    if "bedwetter" not in CFG:
        sys.exit(f"Unable to read from configuration file {config_file}")


def config_update(client):
    """ Updates the config file with any changes that have been made """
    config_file = os.path.expanduser("~/.config/bedwetter/bedwetter.cfg")
    try:
        with open(config_file, "w") as cfg_handle:
            CFG.write(cfg_handle)
    except EnvironmentError:
        log_and_publish(
            client,
            "wateringFailure",
            "Could not write to configuration file {config_file}",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def create_paho_client():
    """ Setup and create a Paho client """
    # Paho is not thread safe, so we'll end up making a few clients
    paho_client = mqtt_client.Client()
    paho_client.tls_set(ca_certs=f"{os.path.dirname(__file__)}/ssl/letsencrypt-root.pem")
    paho_client.username_pw_set(
        CFG["bedwetter"]["mqtt_username"], CFG["bedwetter"]["mqtt_password"],
    )
    return paho_client


def cron_check(kill, skip):
    """ Poll until it is time to trigger a watering """
    LOGGER.info(
        "Started thread to water on schedule (%s)", CFG["bedwetter"]["cron_schedule"]
    )

    cron_client = create_paho_client()
    try:
        cron_client.connect(
            CFG["bedwetter"]["mqtt_server"],
            port=CFG["bedwetter"].getint("mqtt_port"),
            keepalive=60,
        )
    # Paho swallows exceptions so I doubt this even works
    except Exception as paho_e:
        LOGGER.info("Unable to connect to mqtt broker, %s", paho_e)

    cron = CronTab(f'{CFG["bedwetter"]["cron_schedule"]}')
    # The higher this value is, the longer it takes to kill this thread
    sleep_interval = 10
    while True:
        if kill():
            LOGGER.info("Received kill signal, killing cron check thread")
            break
        time_until_cron = cron.next(default_utc=False)
        if CFG["bedwetter"].getboolean("debug"):
            LOGGER.debug("Time until cron: %s seconds", int(time_until_cron))
        if time_until_cron <= sleep_interval:
            # Sleep until it's closer to cron time to avoid a possible race
            sleep(time_until_cron)
            if not skip():
                check_if_watering(cron_client)
            else:
                set_cron_skip(False)
                log_and_publish(
                    cron_client,
                    "wateringSkipped",
                    "Watering skipped",
                    CFG["bedwetter"].getboolean("notify_on_inaction"),
                )
        else:
            sleep(sleep_interval)


def fetch_forecast(client):
    """ Fetch a weather forecast from WeatherFlow """
    try:
        weatherflow_url = (
            "https://swd.weatherflow.com/swd/rest/better_forecast/"
            f'?api_key={CFG["bedwetter"]["weatherflow_api_key"]}'
            f'&lat={CFG["bedwetter"]["latitude"]}&lon={CFG["bedwetter"]["longitude"]}'
        )
        request = requests.get(
            weatherflow_url, timeout=int(CFG["bedwetter"]["timeout"])
        )
        request.encoding = "utf-8"
        return request.json()
    except requests.exceptions.ConnectTimeout:
        log_and_publish(
            client,
            "wateringFailure",
            f'Error: WeatherFlow API timed out after {CFG["bedwetter"]["timeout"]} seconds',
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )
    except requests.exceptions.RequestException:
        log_and_publish(
            client,
            "wateringFailure",
            "Error: There was an error connecting to the WeatherFlow API",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def log_and_publish(client, topic, payload, publish_message=True):
    """ Log a message to the logger, and optionally publish to mqtt """
    LOGGER.info(payload)
    if publish_message:
        publish(client, topic, payload)


def publish(client, topic, payload):
    """ Publish messages to mqtt """
    (return_code, _) = client.publish(
        f'{CFG["bedwetter"]["mqtt_topic"]}/event/{topic}',
        payload=payload,
        qos=0,
        retain=False,
    )
    if return_code != 0:
        LOGGER.error("Unable to publish mqtt message, return code is %s", rc)


def set_cron_skip(value):
    """ Update CRON_SKIP variable and optionally update CRON_THREAD """
    global CRON_SKIP
    LOGGER.info("Setting cron skip value to %s", value)
    CRON_SKIP = value
    if value:
        # If we're setting this to True, we want to update the cron thread also
        CRON_THREAD.join()


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


def water_off(client):
    """ Stop watering """
    try:
        import automationhat
    except ImportError:
        import mock

        automationhat = mock.Mock()
    LOGGER.info("Turning water off")
    automationhat.relay.one.off()
    if not automationhat.relay.one.is_off():
        log_and_publish(
            client, "wateringRunaway", "Watering failed to stop",
        )


def water_on(client, duration):
    """ Start watering """
    try:
        import automationhat
    except ImportError:
        import mock

        automationhat = mock.Mock()
    LOGGER.info("Watering for %s seconds", duration)
    automationhat.relay.one.on()
    sleep(duration)
    if automationhat.relay.one.is_on():
        log_and_publish(
            client,
            "wateringSuccess",
            "Watering succeeded",
            CFG["bedwetter"].getboolean("notify_on_success"),
        )
        CFG["bedwetter"]["last_water"] = f"{time():.0f}"
        config_update(client)
    else:
        log_and_publish(
            client,
            "wateringFailure",
            "Watering failed to start",
            CFG["bedwetter"].getboolean("notify_on_failure"),
        )


def main():
    """ Main """
    # Load config file settings
    config_load()

    # Setup logging
    global LOGGER
    LOGGER = setup_logger()

    # Create main thread mqtt client and setup callbacks
    main_client = create_paho_client()
    main_client.on_connect = cb_on_connect
    main_client.on_disconnect = cb_on_disconnect
    main_client.on_log = cb_on_log
    main_client.on_message = cb_on_message
    try:
        main_client.connect(
            CFG["bedwetter"]["mqtt_server"],
            port=CFG["bedwetter"].getint("mqtt_port"),
            keepalive=60,
        )
    # Paho swallows exceptions so I doubt this even works
    except Exception as paho_e:
        LOGGER.info("Unable to connect to mqtt broker, %s", paho_e)

    log_and_publish(
        main_client,
        "startingUp",
        "Startup has completed",
        CFG["bedwetter"].getboolean("notify_on_service"),
    )

    # Catch SIGTERM when being run via Systemd
    def shutdown(*args):
        log_and_publish(
            main_client,
            "shuttingDown",
            "Caught SIGTERM, shutting down",
            CFG["bedwetter"].getboolean("notify_on_service"),
        )
        # Make sure water is off before we exit
        water_off(main_client)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)

    try:
        main_client.loop_forever()
    except KeyboardInterrupt:
        LOGGER.info("KeyboardInterrupt received, shutting down")
        main_client.disconnect()
        sys.exit(0)


if sys.version_info >= (3, 7):
    if __name__ == "__main__":
        main()
else:
    sys.exit("Fatal Error: This script requires Python 3.7 or greater")
