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

# Standard Library Imports
import os
import sys

# First Party Imports
from configparser import ConfigParser
from time import sleep, time

# Third Party Imports
import requests

try:
    import automationhat
except ImportError:
    print("Unable to import automationhat, continuing in development mode.")

# Global ConfigParser object for configuration options
CFG = ConfigParser()


def config_get_path():
    """ Return the path to the config file """
    return os.path.expanduser("~/.config/bedwetter/bedwetter.cfg")


def config_load():
    """ Load configuration options from file """
    config_file = config_get_path()
    CFG.read(config_file)


def config_update():
    """ Updates the config file with any changes that have been made """
    config_file = config_get_path()

    try:
        with open(config_file, "w") as cfg_handle:
            CFG.write(cfg_handle)
    except EnvironmentError:
        sys.exit("Error: Could not write to configuration file {}".format(config_file))


def fetch_forecast():
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
        sys.exit(
            "Error: Dark Sky API timed out after "
            f'{CFG["bedwetter"]["timeout"]} seconds'
        )
    except requests.exceptions.RequestException:
        sys.exit("Error: There was an error connecting to the Dark Sky API")


def pushover(message, notify):
    """ Send a push notification and exit """
    try:
        if notify:
            requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": CFG["bedwetter"]["pushover_token"],
                    "user": CFG["bedwetter"]["pushover_user"],
                    "message": message,
                },
                timeout=int(CFG["bedwetter"]["timeout"]),
            )
        sys.exit(message)
    except requests.exceptions.Timeout:
        sys.exit(f'Error: Pushover API timed out after {CFG["bedwetter"]["timeout"]}')
    except requests.exceptions.RequestException:
        sys.exit("Error: There was an error connecting to the Pushover API")


def water_on():
    """ Start watering """
    print("Watering for {} seconds.".format(CFG["bedwetter"]["water_duration"]))
    try:
        automationhat.relay.one.on()
        if automationhat.relay.one.is_on():
            sleep(int(CFG["bedwetter"]["water_duration"]))
            CFG["bedwetter"]["last_water"] = f"{time():.0f}"
            config_update()
            return True
    except NameError as name_e:
        print(name_e)
    return False


def water_off():
    """ Stop watering """
    print("Turning water off.")
    try:
        automationhat.relay.one.off()
        if automationhat.relay.one.is_off():
            return True
    except NameError as name_e:
        print(name_e)
    return False


def main():
    """ Main """
    config_load()
    forecast = fetch_forecast()["daily"]["data"][0]
    water = False

    if (
        "precipType" in forecast
        and (forecast["precipProbability"] * 100)
        < int(CFG["bedwetter"]["threshold_percent"])
        and forecast["precipType"] == "rain"
    ):
        print(
            f'{forecast["precipProbability"] * 100:.0f}% chance of '
            f'{forecast["precipType"]} in the next day, time to water.'
        )
        water = True
    elif (int(time()) - int(CFG["bedwetter"]["last_water"])) > (
        86400 * int(CFG["bedwetter"]["threshold_days"])
    ):
        print(
            f'It has been more than {CFG["bedwetter"]["threshold_days"]} '
            "days since last watering, time to water."
        )
        water = True

    if bool(os.getenv("FORCE_WATERING")) or water:
        # Water, notify, and exit.
        if not water_on():
            pushover(
                "Watering failed to start.",
                CFG["bedwetter"].getboolean("notify_on_failure"),
            )

        if not water_off():
            pushover(
                "Watering failed to stop!",
                CFG["bedwetter"].getboolean("notify_on_failure"),
            )

        pushover(
            "Watering was successful.", CFG["bedwetter"].getboolean("notify_on_success")
        )
    else:
        pushover(
            "Not watering today.", CFG["bedwetter"].getboolean("notify_on_inaction")
        )


if sys.version_info >= (3, 7):
    if __name__ == "__main__":
        main()
else:
    sys.exit("Error: This script requires Python 3.7 or greater")
