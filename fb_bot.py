import os
from dotenv import load_dotenv
import requests
from flask import Flask, request


class FbDialogBot(object):

    def __init__(self, fb_token, states_functions, **params):
        self.app = Flask(__name__)
        self.fb_token = fb_token
        self.states_functions = states_functions
        self.app.route('/', methods=['GET'])(self.verify)
        self.app.route('/', methods=['POST'])(self.webhook)

    def verify(self):
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
            if not request.args.get("hub.verify_token") == os.environ['VERIFY_TOKEN']:
                return "Verification token mismatch", 403
            return request.args["hub.challenge"], 200

        return "Hello world", 200

    def webhook(self):
        data = request.get_json()
        if data["object"] == "page":
            for entry in data["entry"]:
                for messaging_event in entry["messaging"]:
                    if messaging_event.get("message"):
                        self.handle_users_reply(messaging_event)

        return "ok", 200

    def handle_users_reply(self, messaging_event):
        sender_id = messaging_event["sender"]["id"]
        recipient_id = messaging_event["recipient"]["id"]
        message_text = messaging_event["message"]["text"]

        user_state = 'SEND_MESSAGE'
        state_handler = self.states_functions[user_state]
        state_handler(self.fb_token, sender_id, message_text)

    def run(self):
        self.app.run(debug=True)


def send_message(fb_token, recipient_id, message_text):
    params = {"access_token": fb_token}
    headers = {"Content-Type": "application/json"}
    request_content = {
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    }
    response = requests.post(
        "https://graph.facebook.com/v2.6/me/messages",
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def main():
    load_dotenv()

    states_functions = {'SEND_MESSAGE': send_message}

    bot = FbDialogBot(os.environ['FACEBOOK_TOKEN'], states_functions)
    bot.run()


if __name__ == '__main__':
    main()
