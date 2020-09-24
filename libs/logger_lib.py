import logging
import telegram


class NotificationLogHandler(logging.Handler):

    def __init__(self, token, chat_id):
        super().__init__()
        self.token = token
        self.chat_id = chat_id

    def emit(self, record):
        log_entry = self.format(record)
        if log_entry:
            bot = telegram.Bot(token=self.token)
            bot.sendMessage(chat_id=self.chat_id, text=log_entry)


def initialize_logger(logger, log_token, chat_id):
    handler = NotificationLogHandler(log_token, chat_id)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
