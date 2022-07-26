# coding=utf-8
from __future__ import absolute_import
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import octoprint.plugin
import flask
import RPi.GPIO as GPIO
import time
import smtplib
import ssl
import requests


class FilamentsensorPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin
):
    counter = 0

    def get_settings_defaults(self):
        return dict(
            gpio_pin=8,
            mode="GPIO.RISING",
            pull_up_down="GPIO.PUD_DOWN",
            send_mail=False,
            mail_html_part="",
            mail_text_part="",
            mail_server="",
            mail_port="",
            mail_user="",
            mail_password="",
            mail_receiver=[],
            webhooks=[]
        )

    def get_assets(self):
        return {
            "js": ["js/filamentsensor.js"],
            "css": ["css/filamentsensor.css"],
        }

    def on_startup(self, *args, **kwargs):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._settings.get(["gpio_pin"]), GPIO.IN, pull_up_down=self._settings.get(["pull_up_down"]))

    def get_update_information(self):
        return {
            "filamentsensor": {
                "displayName": "Filamentsensor Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "JannikHaake",
                "repo": "OctoPrint-FilamentSensor",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/JannikHaake/OctoPrint-FilamentSensor/archive/{target_version}.zip",
            }
        }

    def get_template_configs(self):
        return [
            dict(type="settings", custom_bindings=True)
        ]

    def on_settings_save(self, data):
        GPIO.cleanup()
        GPIO.setup(self._settings.get(["gpio_pin"]), GPIO.IN)
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self.counter = 0
            self._logger.info("Printing started. Filament sensor enabled.")
            self.setup_gpio()
        elif event in (Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED):
            self._logger.info("Printing stopped. Filament sensor disabled.")
            try:
                GPIO.remove_event_detect(self._settings.get(["gpio_pin"]))
            except:
                pass

    def setup_gpio(self):
        try:
            GPIO.remove_event_detect(self._settings.get(["gpio_pin"]))
        except:
            pass
        GPIO.add_event_detect(
            self._settings.get(["gpio_pin"]),
            self._settings.get(["mode"]),
            callback=self.sensor_callback,
            bouncetime=500
        )

    def sensor_callback(self, channel):
        if self.counter == 10:
            self.filament_run_out()
        else:
            self.counter += 1

    def filament_run_out(self):
        self._logger.info("Filament sensor triggered")
        GPIO.remove_event_detect(self._settings.get(["gpio_pin"]))
        if self._printer.is_printing():
            self._printer.toggle_pause_print()
            if self._settings.get(["send_mail"]):
                self.send_mail()

    def send_mail(self):
        message = MIMEMultipart("alternative")
        message["Subject"] = "multipart test"
        message["From"] = sender_email
        message["To"] = receiver_email
        text = self._settings.get(["mail_text_part"])
        html = self._settings.get(["mail_html_part"])
        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            self._settings.get(["mail_server"]),
            self._settings.get(["mail_port"]),
            context=context
        ) as server:
            server.login(self._settings.get(["mail_user"]), self._settings.get(["mail_password"]))
            for receiver in self._settings.get(["mail_receiver"]):
                server.sendmail(
                    self._settings.get(["mail_user"]), receiver, message.as_string()
                )

    def call_webhooks(self):
        for webhook in self._settings.get(["webhooks"]):
            if webhook["enabled"]:
                if webhook["type"] == "post":
                    requests.post(webhook["url"], data=webhook["data"])
                elif webhook["type"] == "get":
                    requests.get(webhook["url"], params=webhook["data"])


__plugin_name__ = "Filamentsensor Plugin"
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentsensorPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
