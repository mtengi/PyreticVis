#!/usr/bin/python

from tornado import websocket, web, httpserver, ioloop
from threading import Thread, Event
import sys

WS_PORT = 8181
WS_PATH = r'/ws'

_pyretic_client = None
_control_client = None
_view_clients = []
_purgatory_clients = []

# Every time a client connects to the server, one of these is spawned
class _ForwardHandler(websocket.WebSocketHandler):

    # Needed for Tornado 4.0: overrides origin check
    # TODO: actually do this correctly
    def check_origin(self, origin):
        return True

    def open(self):
        _purgatory_clients.append(self)  # all clients are ignored until they identify themselves

    def on_message(self, message):
        global _pyretic_client, _control_client
        if message == 'WS_PYRETIC_CLIENT':
            if not _pyretic_client:
                _purgatory_clients.remove(self)
                _pyretic_client = self
            else:
                self.write_message("ERROR: Pyretic client already connected")
                self.close()
        elif message == 'WS_CONTROL_CLIENT':
            if not _control_client:
                _purgatory_clients.remove(self)
                _control_client = self
            else:
                self.write_message("ERROR: Control client already connected")
                self.close()
        elif message == 'WS_VIEW_CLIENT':
            if not self in _view_clients:
                _purgatory_clients.remove(self)
                _view_clients.append(self)
            if _control_client:
                _control_client.write_message('WS_NEW_VIEWER')
        else:
            # process message
            if self == _pyretic_client:
                if _control_client:
                    _control_client.write_message(message)
                for client in _view_clients:
                    client.write_message(message)
            elif self == _control_client:
                if _pyretic_client:
                    _pyretic_client.write_message(message)
            else:
                pass # drop messages from view clients and those in purgatory
        
    def on_close(self):
        global _pyretic_client, _control_client
        if self == _pyretic_client:
            _pyretic_client = None
        if self == _control_client:
            _control_client = None
        if self in _view_clients:
            _view_clients.remove(self)
        if self in _purgatory_clients:
            _purgatory_clients.remove(self)


class _WSForwarder(Thread):
    def __init__(self, ev):
        self.ev = ev
        super(_WSForwarder,self).__init__()

    def run(self):
        application = web.Application([
            (WS_PATH, _ForwardHandler),
        ])
        http_server = httpserver.HTTPServer(application)
        http_server.listen(WS_PORT)
        #print 'websocket forwarder starting on port %s' % WS_PORT
        self.ev.set()
        ioloop.IOLoop.instance().start()

def start_ws_forwarder():
    # The thread takes a little while to start, so use an event to signal that it's ready
    ev = Event()
    t = _WSForwarder(ev)
    t.daemon = True
    t.start()
    ev.wait()
    return t

if __name__ == '__main__':
    start_ws_forwarder().join()
