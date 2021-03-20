import collections.abc
import os
import re
from collections import OrderedDict
from typing import Dict, Any

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from telegram.ext import Updater, PicklePersistence, CallbackContext, CallbackQueryHandler, ConversationHandler
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





class NestedValue(object):
    """Utility class to read/write access to value of nested object
    For example:
        `NestedValue(d, '/a/b/c.foo').value = 67`
        is equivalent to
        `d.setdefault('a', {}).setdefault('b', {}).get('c', None).foo(67)`
        if foo is a function or equivalent to
        `d.setdefault('a', {}).setdefault('b', {}).get('c', None).foo = 67`
        if foo is a attribute
    """
    def __init__(self, storage, path):
        self._storage = storage
        self._path = path

    @property
    def value(self):
        storage = self._storage
        for key in self._path.split('/'):
            if not key:
                continue
            if '.' in key:
                key, attr = key.split('.')
            else:
                attr = None
            storage = storage.get(key, None)
            if storage and attr and hasattr(storage, attr):
                if callable(getattr(storage, attr)):
                    storage = getattr(storage, attr)()
                else:
                    storage = getattr(storage, attr)
        return storage

    @value.setter
    def value(self, value):
        storage = self._storage
        target_path, target_name = os.path.split(self._path)

        if not target_name:
            return

        for key in target_path.split('/'):
            if not key:
                continue
            if '.' in key:
                key, attr = key.split('.')
            else:
                attr = None
            storage = storage.setdefault(key, {})
            if attr and hasattr(storage, attr):
                if callable(getattr(storage, attr)):
                    storage = getattr(storage, attr)()
                else:
                    storage = getattr(storage, attr)

        if '.' in target_name:
            target_name, attr = target_name.split('.')
            storage = storage.get(target_name)
            if attr and hasattr(storage, attr):
                if callable(getattr(storage, attr)):
                    return getattr(storage, attr)(value)
                else:
                    return setattr(storage, attr, value)
        else:
            storage[target_name] = value
            return value


def user_message(update, context):
    awaiting_data = context.user_data.setdefault('awaiting_data', [])
    if awaiting_data:
        value_target_path, _, call_after = awaiting_data.pop(0)
        if value_target_path in globals():
            value_target_path = globals().get(value_target_path)
            value_target_path(update, context, update.message.text)
        else:
            NestedValue(context.user_data, value_target_path).value = update.message.text
        update.message.reply_text('Got it!')

        if call_after:
            if call_after in globals():
                call_after = globals().get(call_after)
            if callable(call_after):
                call_after(update, context)
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


def gmail_flow(oauth2_state=None):
    return Flow.from_client_secrets_file(
        client_secrets_file=settings['access']['google_api']['oauth20_secret_file'],
        scopes=['https://www.googleapis.com/auth/gmail.modify'],
        redirect_uri='urn:ietf:wg:oauth:2.0:oob',
        state=oauth2_state
    )


def gmail_auth_check(update, context):
    credentials = context.user_data.get('gmail', {}).get('credentials', None)
    if not credentials:
        return False, 'No credentials'

    if not credentials.valid:
        if credentials.expired:
            if not credentials.refresh_token:
                return False, "Credentials has been expired but doesn't have refresh token"
            else:
                credentials.refresh(Request())
                return True, 'Credentials has been updated'
        return False, 'Credentials are not valid'
    return True, 'Ok'


def gmail_auth_url(update, context):
    gmail_settings = context.user_data.setdefault('gmail', {})
    url, gmail_settings['oauth2_state'] = gmail_flow().authorization_url(prompt='consent')
    return url


def gmail_auth_confirm(update, context, code):
    gmail_settings = context.user_data.setdefault('gmail', {})
    flow = gmail_flow(gmail_settings['oauth2_state'])
    flow.fetch_token(code=code)
    gmail_settings['credentials'] = flow.credentials
    return gmail_auth_check(update, context)


def gmail_auth_reset(update, context):
    gmail_settings = context.user_data.setdefault('gmail', {})
    del gmail_settings['credentials']


def gmail_api(update, context):
    if gmail_auth_check(update, context)[0]:
        gmail_settings = context.user_data.setdefault('gmail', {})
        return build('gmail', 'v1', credentials=gmail_settings['credentials'])
    return None


def gmail_labels(update, context):
    # type: (Update, CallbackContext) -> None

    if gmail_auth_check(update, context)[0]:
        api = gmail_api(update, context)
        response = api.users().labels().list(userId='me').execute()
        reply_text = ''
        for label in response.get('labels', []):
            reply_text += f"{label['name']} ({label['id']})\n"
        update.message.reply_text(reply_text)
    else:
        auth_url = gmail_auth_url(update, context)
        message = f'Please send me the auth code that you get from the link: {auth_url}'
        context.user_data.setdefault('awaiting_data', []).append(
            ('gmail/auth_code', message, None)
        )
        update.message.reply_text(message)


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
                 'Please send me the URL address of Redmine service', None)
            )
        if not redmine_auth_key:
            context.user_data.setdefault('awaiting_data', []).append(
                ('redmine/auth_key',
                 'Please send me the your auth key/token of Redmine service', None)
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
                 'Please send me the URL address of OTRS service', None)
            )
        if not otrs_username:
            context.user_data.setdefault('awaiting_data', []).append(
                ('otrs/username',
                 'Please send me the your username for OTRS service', None)
            )
        if not otrs_password:
            context.user_data.setdefault('awaiting_data', []).append(
                ('otrs/password',
                 'Please send me the your password for OTRS service', None)
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


def reply_or_send(update, context, *args, **kwargs):
    if update.message:
        update.message.reply_text(*args, **kwargs)
    else:
        context.bot.send_message(update.effective_user.id, *args, ** kwargs)


def demo(update, context):
    # type: (Update, CallbackContext) -> None

    q = update.callback_query
    path = q.data if q else ''
    path = path or os.sep

    rows = []
    if path == os.sep:
        rows.append([menu_button(path, 'gmail')])
    elif path.startswith('/gmail'):
        if path == '/gmail':
            rows.append([menu_button(path, 'auth')])
            rows.append([menu_button(path, 'labels')])
            rows.append([menu_button(path, 'service')])
        elif path.startswith('/gmail/auth'):
            if path == '/gmail/auth/reset':
                gmail_auth_reset(update, context)
            elif path == '/gmail/auth/code':
                message = 'Please send me the auth code that you get from the link'
                context.user_data.setdefault('awaiting_data', []).append(
                    ('gmail_auth_confirm', message, 'demo')
                )
                context.bot.send_message(update.effective_user.id, message)

            if gmail_auth_check(update, context)[0]:
                rows.append([menu_button(path, 'reset')])
            else:
                auth_url = gmail_auth_url(update, context)
                rows.append([menu_button(path, auth_url, 'Sign in (get auth code)', is_url=True)])
                rows.append([menu_button(path, 'code')])
        elif path.startswith('/gmail/labels'):
            if gmail_auth_check(update, context)[0]:
                response = gmail_api(update, context).users().labels().list(userId='me').execute()
                reply_text = ''
                for label in response.get('labels', []):
                    rows.append([menu_button(path, '..', f"{label['name']} ({label['id']})\n")])
                # reply_or_send(update, context, text=reply_text)
    elif path == '/gmail/service':
        rows.append([menu_button(path, 'redmine')])
        rows.append([menu_button(path, 'otrs')])

    if path != os.sep:
        rows.append([menu_button(path, '..', 'back')])

    if q:
        q.answer(path)
        q.edit_message_text('test', reply_markup=InlineKeyboardMarkup(rows))
    else:
        reply_or_send(update, context, 'Nice', reply_markup=InlineKeyboardMarkup(rows))


################

TOP_MENU = 'TOP_MENU'
GMAIL_MENU = 'GMAIL_MENU'
REDMINE_MENU = 'REDMINE_MENU'
OTRS_MENU = 'OTRS_MENU'


def start(update, context):
    user = update.effective_user
    chat = update.effective_chat
    update.message.reply_markdown(f'Hello, {user.username}!\n'
                                  f'Your user ID is `{user.id}`'
                                  f' and out chat ID is `{chat.id}`')
    rows = [
        [InlineKeyboardButton('GMail', callback_data='gmail')],
        [InlineKeyboardButton('Redmine', callback_data='redmine')],
        [InlineKeyboardButton('Otrs', callback_data='otrs')],
    ]
    update.message.reply_text('Choose service', reply_markup=InlineKeyboardMarkup(rows))
    return TOP_MENU


def top_menu_handler(update, context):
    q = update.callback_query
    q.answer()

    rows = []
    if q.data == GMAIL_MENU:
        auth_prefix =
        rows.append([InlineKeyboardButton('')])

    return q.data




conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        TOP_MENU: [CallbackQueryHandler(top_menu_handler)]
    },
    fallbacks=[CommandHandler('start', start)]
)
dispatcher.add_handler()
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
