import collections.abc
import os
from typing import Dict, Any

from google_auth_httplib2 import Request
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, PicklePersistence, CallbackContext
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext import Filters
import yaml
import logging, logging.config
import sys
import threading
from google_auth_oauthlib.flow import Flow


# default settings
settings: Dict[str, Any] = {
    'access': {
        'token': None,
        'god_id_list': [],
        'google_api': {
            'oauth20_secret_file': None
        }
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
    if not isinstance(update_dict, collections.abc.Mapping):
        return target_dict
    for k, v in update_dict.items():
        if isinstance(v, collections.abc.Mapping):
            target_dict[k] = recursive_update(target_dict.get(k, {}), v)
        else:
            target_dict[k] = v
    return target_dict


if os.path.exists('conf.yml'):
    with open('conf.yml', 'rt') as conf:
        recursive_update(settings, yaml.safe_load(conf))
else:
    with open('conf.yml', 'wt') as conf:
        yaml.dump(settings, conf)


logging.config.dictConfig(settings['logging'])


if not settings['access']['token']:
    logging.error('Empty bot token in conf.yml (`access/token`)')
    sys.exit(1)


data_storage = PicklePersistence('bot.data')
updater = Updater(token=settings['access']['token'],
                  persistence=data_storage,
                  use_context=True)
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
    update.message.reply_text("I don't understand what you mean, that's why I've logged your message")


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


def code(update, context):
    # type: (Update, CallbackContext) -> None
    if context.args:
        context.user_data['auth_code'] = context.args[0]
        update.message.reply_text(f'Got it!')
    else:
        update.message.reply_text(f'Empty code')


def gmail_labels(update, context):
    # type: (Update, CallbackContext) -> None

    user = update.effective_user

    credentials = None
    token_filename = f'{user.id}.json'
    logger = logging.getLogger()

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    credentials = context.user_data.get('credentials', None)

    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            logger.debug(f'updating existing credentials')
            credentials.refresh(Request())
        else:
            logger.debug(f'requesting credentials')
            oauth_secret_filename = settings['access']['google_api']['oauth20_secret_file']
            flow = Flow.from_client_secrets_file(
                oauth_secret_filename,
                scopes=['https://www.googleapis.com/auth/gmail.modify'],
                redirect_uri='urn:ietf:wg:oauth:2.0:oob')

            user_code = context.user_data.get('auth_code', None)
            if user_code:
                del context.user_data['auth_code']
                # The user will get an authorization code. This code is used to get the
                # access token.
                flow.fetch_token(code=user_code)
                credentials = flow.credentials
            else:
                # Tell the user to go to the authorization URL.
                auth_url, _ = flow.authorization_url(prompt='consent')
                update.message.reply_markdown('To continue, you have to '
                                              'sign in to your Google account '
                                              'and allow access.\n'
                                              'As a result, you''ll receive confirmation code '
                                              'which you have to send to me '
                                              'in a *PRIVATE* chat by command /code',
                                              reply_markup=InlineKeyboardMarkup([
                                                  [InlineKeyboardButton('Sign in and get code ...',
                                                                        url=auth_url
                                                                        )]
                                              ]))
                return
    context.user_data['credentials'] = credentials

    logger.debug(f'building api instance')
    gmail_api = build('gmail', 'v1', credentials=credentials)
    response = gmail_api.users().labels().list(userId='me').execute()
    reply_text = ''
    for label in response.get('labels', []):
        reply_text += f"{label['name']} ({label['id']})\n"
    update.message.reply_text(reply_text)


def error_handler(update: Update, context: CallbackContext):
    update.message.reply_text(f'Internal exception: {context.error.message}')
    raise context.error


dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('die', die))
dispatcher.add_handler(CommandHandler('code', code))
dispatcher.add_handler(CommandHandler('gmail_labels', gmail_labels))
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.status_update, message_logger))

dispatcher.add_error_handler(error_handler)

logging.info('start polling...')
updater.start_polling()
updater.idle()
