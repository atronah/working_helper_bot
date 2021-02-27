import collections.abc
import os
import re
from collections import OrderedDict
from typing import Dict, Any

from google_auth_httplib2 import Request
from googleapiclient.discovery import build, Resource
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from telegram.ext import Updater, PicklePersistence, CallbackContext, CallbackQueryHandler
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


def user_message(update, context):
    awaiting_data = context.user_data.setdefault('awaiting_data', [])
    if awaiting_data:
        value_path, _ = awaiting_data.pop(0)
        value_dict = context.user_data
        key_list = value_path.split('/')
        for key in key_list[:-1]:
            value_dict = value_dict.setdefault(key, {})
        value_dict[key_list[-1]] = update.message.text
        update.message.reply_text('Got it!')
        if awaiting_data:
            update.message.reply_text(awaiting_data[0][1])
    else:
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


def callbacks_handler(update, context):
    # type: (Update, CallbackContext) -> None

    q = update.callback_query
    answer = None
    if q.data == 'awaiting_data':
        answer = 'I am waiting for your answer'
        awaiting_data = context.user_data.get('awaiting_data', [])
        if awaiting_data:
            message = awaiting_data[0][1]
        else:
            message = answer
        update.effective_user.send_message(message)
    q.answer(answer)


def markdown_escape(text, escape_chars=r'_*[]()~`>#+-=|{}.!'):
    """based on telegram.utils.helpers.escape_markdown"""
    return re.sub('([{}])'.format(re.escape(escape_chars)), r'\\\1', text)


def format_time(h=0, m=0):
    if h is None or m is None:
        return '-'
    return f'{(int(h) + (m // 60)):02}:{int((60 * h + m) % 60):02}'



def gmail_flow(update, context):
    # type: (Update, CallbackContext) -> [Flow]

    user_gmail_settings = context.user_data.get('gmail', {})

    oauth_secret_filename = settings['access']['google_api']['oauth20_secret_file']
    return Flow.from_client_secrets_file(
        oauth_secret_filename,
        scopes=['https://www.googleapis.com/auth/gmail.modify'],
        redirect_uri='urn:ietf:wg:oauth:2.0:oob',
        state=user_gmail_settings.get('oauth2_state', 'None')
    )

def gmail_sign_in(update, context):
    # type: (Update, CallbackContext) -> str

    user_gmail_settings = context.user_data.get('gmail', {})
    flow = gmail_flow(update, context)

    auth_url, user_gmail_settings['oauth2_state'] = flow.authorization_url(prompt='consent')

    return auth_url


def gmail(update, context):
    # type: (Update, CallbackContext) -> [None, Resource]

    logger = logging.getLogger()
    gmail_settings = context.user_data.get('gmail', {})

    credentials = gmail_settings.get('credentials', None)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            logger.debug(f'updating existing credentials')
            credentials.refresh(Request())
        else:
            logger.debug(f'requesting credentials')
            flow = gmail_flow(update, context)

            if 'auth_code' in gmail_settings:
                auth_code = gmail_settings.pop('auth_code')
                flow.fetch_token(code=auth_code)
                credentials = flow.credentials
                gmail_settings['credentials'] = credentials
            else:
                auth_url, gmail_settings['oauth2_state'] = flow.authorization_url(prompt='consent')
                context.user_data.setdefault('awaiting_data', []).append(
                    ('gmail/auth_code',
                     'Please send me the auth code that you get from the link')
                )
                if update.effective_chat.type is not 'private':
                    message = markdown_escape('Authentication required!'
                                              ' Please, go to the in a'
                                              ' [PRIVATE](https://t.me/a_work_assistant_bot) chat'
                                              ' to pass authentication process',
                                              r'!')
                    update.message.reply_markdown_v2(message)
                private_message = markdown_escape('To continue, you have to '
                                                  'sign in to your Google account '
                                                  'and allow requested access for that bot.\n'
                                                  'As a result, you''ll receive confirmation code '
                                                  'which you have to send to me in that chat.'
                                                  , r'.')
                private_reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton('Sign in to Google', url=auth_url, callback_data='awaiting_data')]
                ])
                update.effective_user.send_message(private_message,
                                                   parse_mode=ParseMode.MARKDOWN_V2,
                                                   reply_markup=private_reply_markup)
                return None
    gmail_api = build('gmail', 'v1', credentials=credentials)
    return gmail_api


def gmail_labels(update, context):
    # type: (Update, CallbackContext) -> None

    gmail_api = gmail(update, context)
    if gmail_api:
        response = gmail_api.users().labels().list(userId='me').execute()
        reply_text = ''
        for label in response.get('labels', []):
            reply_text += f"{label['name']} ({label['id']})\n"
        update.message.reply_text(reply_text)


def redmine(update, context):
    # type: (Update, CallbackContext) -> None

    from redminelib import Redmine

    redmine_settings = context.user_data.get('redmine', {})
    redmine_address = redmine_settings.get('address', None)
    redmine_auth_key = redmine_settings.get('auth_key', None)

    if redmine_address and redmine_auth_key:
        r = Redmine(redmine_address, key=redmine_auth_key)
        issues = ','.join(context.args).split(',')
        message = ''
        for i in issues:
            try:
                d = r.issue.get(i)
                message += f'#{i}: {getattr(d, "subject", "-")}\n'
                message += f'|___>[{getattr(d, "status", "-")}] ' \
                           f'Assigned: {getattr(d, "assigned_to", "-")} ' \
                           f'(Spent time: {format_time(getattr(d, "total_spent_hours", 0))})\n'
                for t in d.time_entries:
                    message += f'    |___>{t.spent_on} {t.user} ({t.hours} hours, {format_time(t.hours)})\n'
            except Exception as e:
                message += f'#{i}: {e}\n'
        update.message.reply_text(message)
    else:
        if update.effective_chat.type is not 'private':
            public_chat_message = markdown_escape("Access to Redmine hasn't setup yet!"
                                                  ' Please, go to the in a'
                                                  ' [PRIVATE](https://t.me/a_work_assistant_bot) chat'
                                                  ' to setup it.',
                                                  r'!.')
            update.message.reply_markdown_v2(public_chat_message)

        if not redmine_address:
            context.user_data.setdefault('awaiting_data', []).append(
                ('redmine/address',
                 'Please send me the URL address of Redmine service')
            )
        if not redmine_auth_key:
            context.user_data.setdefault('awaiting_data', []).append(
                ('redmine/auth_key',
                 'Please send me the your auth key/token of Redmine service')
            )
        private_message = markdown_escape('To continue, you have to '
                                          'send me some data to access Redmine.'
                                          , r'.')
        update.effective_user.send_message(private_message,
                                           parse_mode=ParseMode.MARKDOWN_V2)
        update.effective_user.send_message(context.user_data['awaiting_data'][0][1])


def otrs(update, context):
    # type: (Update, CallbackContext) -> None

    from otrs.ticket.template import GenericTicketConnectorSOAP
    from otrs.client import GenericInterfaceClient
    from otrs.ticket.objects import Ticket, Article, DynamicField, Attachment

    otrs_settings = context.user_data.get('otrs', {})
    otrs_address = otrs_settings.get('address', None)
    otrs_username = otrs_settings.get('username', None)
    otrs_password = otrs_settings.get('password', None)
    webservice_name = 'GenericTicketConnectorSOAP'

    if otrs_address and otrs_username and otrs_password:
        client = GenericInterfaceClient(otrs_address, tc=GenericTicketConnectorSOAP(webservice_name))
        client.tc.SessionCreate(user_login=otrs_username, password=otrs_password)

        issues = [int(i) for i in ','.join(context.args).split(',') if i.isdigit()]
        message = ''
        for i in issues:
            try:
                ticket = client.tc.TicketGet(i, get_articles=False, get_dynamic_fields=True, get_attachments=False)
                title = ticket.attrs.get('Title', '-')
                state = ticket.attrs.get('State', '-')
                plan_time_str = ticket.attrs.get('DynamicField_Plantime', None)
                plan_time = int(plan_time_str) if plan_time_str is not None else None
                formated_time = format_time(m=plan_time)
                message += f'[{state}] #{i:06} - {title} ({formated_time})\n'
            except Exception as e:
                message += f'#{i}: {e}'
        update.message.reply_text(message)
    else:
        if update.effective_chat.type is not 'private':
            public_chat_message = markdown_escape("Access to OTRS hasn't setup yet!"
                                                  ' Please, go to the in a'
                                                  ' [PRIVATE](https://t.me/a_work_assistant_bot) chat'
                                                  ' to setup it.',
                                                  r'!.')
            update.message.reply_markdown_v2(public_chat_message)

        if not otrs_address:
            context.user_data.setdefault('awaiting_data', []).append(
                ('otrs/address',
                 'Please send me the URL address of OTRS service')
            )
        if not otrs_username:
            context.user_data.setdefault('awaiting_data', []).append(
                ('otrs/username',
                 'Please send me the your username for OTRS service')
            )
        if not otrs_password:
            context.user_data.setdefault('awaiting_data', []).append(
                ('otrs/password',
                 'Please send me the your password for OTRS service')
            )
        private_message = markdown_escape('To continue, you have to '
                                          'send me some data to access OTRS.'
                                          , r'.')
        update.effective_user.send_message(private_message,
                                           parse_mode=ParseMode.MARKDOWN_V2)
        update.effective_user.send_message(context.user_data['awaiting_data'][0][1])


def error_handler(update: Update, context: CallbackContext):
    context.bot.send_message(update.effective_chat.id,
                             f'Internal exception: {str(context.error)}')
    raise context.error


def menu_button(path, data, text=None, is_url=False):
    callback_data = None if is_url else os.path.normpath(os.path.join(path, data))
    url = data if is_url else None
    return InlineKeyboardButton(text or data, callback_data=callback_data, url=url)
        


def demo(update, context):
    # type: (Update, CallbackContext) -> None

    q = update.callback_query
    path = q.data if q else ''
    path = path or os.sep

    rows = []
    if path == os.sep:
        rows.append([menu_button(path, 'gmail')])
    elif path == '/gmail':
        rows.append([menu_button(path, 'auth')])
        rows.append([menu_button(path, 'service')])
    elif path.startswith('/gmail/auth'):
        user_gmail_settings = context.user_data.get('gmail', {})
        gmail_credentials = user_gmail_settings.get('credentials')
        if gmail_credentials and gmail_credentials.valid:
            rows.append([menu_button(path, 'reset')])
        elif gmail_credentials and gmail_credentials.expired and gmail_credentials.refresh_token:
            rows.append([menu_button(path, 'refresh')])
        else:
            auth_url = gmail_sign_in(update, context)
            rows.append([menu_button(path, auth_url, 'Sign in (get auth code)', is_url=True)])
            rows.append([menu_button(path, 'code')])
        if path == '/gmail/auth/code':
            message = 'Please send me the auth code that you get from the link'
            context.user_data.setdefault('awaiting_data', []).append(
                ('gmail/auth_code', message)
            )
            context.bot.send_message(update.effective_user.id, message)
        elif path == '/gmail/auth/refresh':
            message = 'Please send me the auth code that you get from the link'
            context.user_data.setdefault('awaiting_data', []).append(
                ('gmail/auth_code', message)
            )
            context.bot.send_message(update.effective_user.id, message)
        elif path == '/gmail/auth/reset':
            del user_gmail_settings['credentials']
    elif path == '/gmail/service':
        rows.append([menu_button(path, 'redmine')])
        rows.append([menu_button(path, 'otrs')])

    if path != os.sep:
        rows.append([menu_button(path, '..', 'back')])

    if q:
        q.answer(path)
        q.edit_message_text('test', reply_markup=InlineKeyboardMarkup(rows))
    else:
        update.message.reply_text('Nice', reply_markup=InlineKeyboardMarkup(rows))






dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('die', die))
dispatcher.add_handler(CommandHandler('gmail_labels', gmail_labels))
dispatcher.add_handler(CommandHandler('redmine', redmine))
dispatcher.add_handler(CommandHandler('otrs', otrs))
dispatcher.add_handler(CommandHandler('demo', demo))
dispatcher.add_handler(CallbackQueryHandler(demo, '/.*'))
dispatcher.add_handler(CallbackQueryHandler(callbacks_handler))

dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.status_update, user_message))

dispatcher.add_error_handler(error_handler)

logging.info('start polling...')
updater.start_polling()
updater.idle()
