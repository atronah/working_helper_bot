from telegram.ext import Updater
from telegram.ext import CommandHandler
import yaml
import logging, logging.config
import sys

# default settings
settings = {
    'access': {
        'token': None
    },
    'logging': {
        'version': 1.0,
        'formatters': {
            'default': {
                'format': '[{asctime}]{levelname: <5}({name}): {message}',
                'style': '{'
            }
        },
        'handlers': {
            'general': {
                'class': 'logging.handlers.WatchedFileHandler',
                'level': 'INFO',
                'filename': 'bot.log',
                'formatter': 'default'
            },
            'unknown_messages': {
                'class': 'logging.handlers.WatchedFileHandler',
                'level': 'DEBUG',
                'filename': 'unknown_messages.log',
                'formatter': 'default'
            }
        },
        'loggers': {
            'unknown_messages': {
                'level': 'DEBUG',
                'handlers': ['unknown_messages']
            }
        },
        'root': {
            'level': 'INFO',
            'handlers': ['general']
        },
    }
}

with open('conf.yml') as conf:
    settings.update(yaml.safe_load(conf))


logging.config.dictConfig(settings['logging'])

if not settings['access']['token']:
    logging.error('Empty bot token in conf.yml (`access/token`')
    sys.exit(1)


updater = Updater(token=settings['access']['token'], use_context=True)
dispatcher = updater.dispatcher

def hello(update, context):
    user = update.effective_user
    chat = update.effective_chat
    update.message.reply_markdown(f'Hello, {user.username}!\n'
                              f'Your user ID is `{user.id}`'
                              f' and out chat ID is `{chat.id}`')


dispatcher.add_handler(CommandHandler('hello', hello))

logging.info('start polling...')
updater.start_polling()
