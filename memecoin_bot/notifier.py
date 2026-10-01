"""Notifications Telegram (mêmes secrets que le bot de news). Sans token : affichage console."""
import requests


class Notifier:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, chat_id

    def send(self, text):
        print(text.replace("\n", " | "))
        if not self.token or not self.chat_id:
            return
        try:
            requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage", timeout=15,
                          data={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"})
        except Exception as ex:
            print("! Telegram:", ex)
