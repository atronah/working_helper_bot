#   /gmail - menu/resource
#       /auth - menu/resource
#           /sign_in - link (+ auto use ./code)
#           /code - value setter
#           /reset - action
#       /service - menu/resource
#           /[redmine] - menu/resource
#               /email -
#                   /[email_id]
#                       /ticket
#                       /[ticket_id]
#                           /... (move_to, move_to_last_selected, ...)
#                       /move_to - menu-selector
#                           /[label_id]
#                       /move_to_last_selected
#                       [first][prev][num/all][next][last]
#               /ticket
#                   /[ticket_id]
#                       /email
#                           /[email_id]
#                               /... (move_to, move_to_last_selected, ...)
#                       /move_to - menu-selector
#                           /[label_id]
#                       /move_to_last_selected
#                       [first][prev][num/all][next][last]
#               /settings - menu/resource
#                   /from - value setter
#           /[otrs]

# https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/resources.html#resources-which-implement-interfaces


class GMail(object):
    def __init__(self):
        self._services = []
        self._credentials

    @property
    def authorised(self):
        return False

    def connect_ticket_service(self, service: TicketService):
        pass

    def sort_mail(self):
        pass

    def auth(self, code=None):
        pass




