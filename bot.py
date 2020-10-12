import collections

from telegram.ext import Updater
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext import Filters
import yaml
import logging, logging.config
import sys
import threading

# default settings
settings = {
    'access': {
        'token': None,
        'god_id_list': []
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
            'stdout': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
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


def recursive_update(target_dict, update_dict):
    for k, v in update_dict.items():
        if isinstance(v, collections.abc.Mapping):
            target_dict[k] = recursive_update(target_dict.get(k, {}), v)
        else:
            target_dict[k] = v
    return target_dict


with open('conf.yml') as conf:
    recursive_update(settings, yaml.safe_load(conf))


logging.config.dictConfig(settings['logging'])


if not settings['access']['token']:
    logging.error('Empty bot token in conf.yml (`access/token`')
    sys.exit(1)


updater = Updater(token=settings['access']['token'], use_context=True)
dispatcher = updater.dispatcher


def start(update, context):
    user = update.effective_user
    chat = update.effective_chat
    update.message.reply_markdown(f'Hello, {user.username}!\n'
                                  f'Your user ID is `{user.id}`'
                                  f' and out chat ID is `{chat.id}`')


def message_logger(update, context):
    logger = logging.getLogger('unknown_messages')
    logger.debug(f'{update.effective_user.id} {update.message.text}')
    update.message.reply_text("I don't understand what you mean, that''s why I've logged your message")


def shutdown():
    updater.stop()
    updater.is_idle = False


def die(update, context):
    user = update.effective_user
    if user.id in settings['access']['god_id_list']:
        update.message.reply_text('My fight is over!')
        threading.Thread(target=shutdown).start()
    else:
        logging.warning(f'unauthorized attempt to kill: {user.name} (id={user.id})')
        update.message.reply_text('Sorry, but you have no power to kill me.')


dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('die', die))
dispatcher.add_handler(MessageHandler(Filters.all, message_logger))


logging.info('start polling...')
updater.start_polling()
updater.idle()
