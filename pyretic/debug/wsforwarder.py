#!/usr/bin/python

from tornado import websocket, web, httpserver, ioloop
from threading import Thread
import sys

WS_PORT = 8181
WS_PATH = r'/ws'

_clients = []

# Every time a client connects to the server, one of these is spawned
class _ForwardHandler(websocket.WebSocketHandler):
    def open(self):
        if len(_clients) >= 2:
            #print "got additional client request"
            self.write_message("too many clients. Connection refused")
            self.close()
        else:
            #print "got new client"
            _clients.append(self)

    def on_message(self, message):
        if len(_clients) != 2:
            #self.write_message('No other clients. Message dropped')
            return

        if _clients[0] == self:
            _clients[1].write_message(message)
        else:
            _clients[0].write_message(message)

    def on_close(self):
        if self in _clients:
            _clients.remove(self)


class _WSForwarder(Thread):
    def run(self):
        application = web.Application([
            (WS_PATH, _ForwardHandler),
        ])
        http_server = httpserver.HTTPServer(application)
        http_server.listen(WS_PORT)
        #print 'websocket forwarder starting on port %s' % WS_PORT
        ioloop.IOLoop.instance().start()

def start_ws_forwarder():
    t = _WSForwarder()
    t.daemon = True
    t.start()
    return t

if __name__ == '__main__':
    start_ws_forwarder().join()
