
# Bedwetter

## About

I wrote this code to automate watering of my raised beds from a rain barrel using
Raspberry Pi Zero W, and a [Pimoroni Automation pHAT](https://shop.pimoroni.com/products/automation-phat).

When run out of crontab, it will determine if it should water the gardens and activate
the relay on the Automation Phat board, which runs a 24v submersible pump in the rain barrel.
The rain barrel's spigot is hooked up to soaker hoses in the beds.

## Configuration

The Automation pHAT requires that I2C be enabled on the Raspberry Pi, which can be done in `raspi-config`
under the `Interfacing Options` section.

Bedwetter is configured via a config file that should reside at `${HOME}/.config/bedwetter/bedwetter.cfg`
and contains something along the lines of:

```ini
[bedwetter]
darksky_api_key = <Your Dark Sky API key>
latitude = <The latitude of your garden>
longitude = <The longitude of your garden>
notify_on_failure = true
notify_on_inaction = true
notify_on_success = true
pushover_token = <Your Pushover API secret>
pushover_user = <Your Pushover API user key>
threshold_days = 2
threshold_percent = 50
timeout = 5
water_duration = 300
```

It should be noted that this project is a bit rough around the edges as I didn't really
intend to distribute it, but I thought people might be interested in it.
