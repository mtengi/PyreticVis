import networkx as nx
import json
from networkx.readwrite import json_graph
from websocket import create_connection
import socket
import threading
import logging
import time
from pyretic.debug.wsforwarder import *

WS_URL = 'ws://localhost:%d%s' % (WS_PORT, WS_PATH)

class NetVis():
    def __init__(self, net):
        self.curr_topo = None
        self.log = logging.getLogger('%s.NetVis' % __name__)
        self.updates = []


    #TODO: add mininet features
    def initialize_from_mininet(self):
        pass

    # Take the topology (assumed to be complete and connected) and 
    def initialize_from_topo(self, topo):
        nodes = []
        links = []
        print 'init from topo'
        for n in topo.node:
           print n


class Link(object):
    def __init__(self, name, nodes = (None, None), status = 'connected', capacity = None):
        self.id = id(self)

        self.name = name
        self.status = status
        self.capacity = capacity
        self.nodes = nodes

        # A link must be made between two existing Nodes. 
        if not self.nodes[0] or not self.nodes[1] or len(self.nodes) != 2:
            raise Exception # TODO: handle this better

        if not self.status == 'connected' or self.status == 'disconnected':
            raise Exception # TODO: same as above

    def connect(self):
        self.status = up

    def disconnect(self):
        self.status = down



    def __repr__(self):
        return id(self)

    def __str__(self):
        return repr(self)


class Node(object):
    def __init__(self, **opts):
        self.id = id(self) # Maybe a little too hacky?
        # A dictionary of the form { port_no : Link }
        self.links = {}

        # Allow arbitrary data on the Node
        for k,v in opts.iteritems():
            setattr(self, k, v)

    def add_link(self, link, port_no):
        if link == null:
            self.links.pop(port_no)
        else:
            self.links[port_no] = link

    def set_prop(self, prop, value):
        setattr(self, prop, value)

    def __repr__(self):
        return str(id(self))

    def __str__(self):
        return repr(self)


class Switch(Node):
    def __init__(self, name):
        super(Switch,self).__init__(name)
        self.ports_to_links = {}

    def add_port(self, portnum):
        assert not self.ports_to_links.has_key(portnum),"Port %d already exists in switch %s!" % (portnum, self.name)
        self.ports_to_links[portnum] = None

class Network(object):
    def __init__(self):
        self.nodes = []
        self.links = []

    def add_node():
        pass


from pyretic.core.runtime import ConcreteNetwork

##actually use this
# maybe take CN class and store it here, so we can have the superclass distinct from runtime.ConcreteNetwork
# problem is that it looks for the superclass at the time of initialization. by that point, VCN is its own superclass

# slightly more modular: if this is second recursive call to VCN.__init__, directly call Network.__init__. That would stop infinite recursion and not need to paste entire CN.__init__ here

#newest idea: merge visualizer functionality into this class. this will just make everything easier
class VisConcreteNetwork(ConcreteNetwork):
    def __init__(self, runtime=None):
        
        # Instead of calling super(VisConcreteNetwork,self).__init__().
        # That doesn't work because superclasses get messed up when changing
        # runtime.ConcreteNetwork to this class
        super(ConcreteNetwork,self).__init__()
        self.next_topo = self.topology.copy()
        self.runtime = runtime
        self.wait_period = 0.25
        self.update_no_lock = threading.Lock()
        self.update_no = 0
        self.log = logging.getLogger('%s.ConcreteNetwork' % __name__)
        self.debug_log = logging.getLogger('%s.DEBUG_TOPO_DISCOVERY' % __name__)
        self.debug_log.setLevel(logging.DEBUG)

        # The WebScoket over which we'll communicate with the browser
        self.ws = self.connect()

        # Obects in the network, indexed by number (the number given by Pyretic)
        self.switches = {}
        self.links = {}
        self.egresses = {}

        # Maintain a list of actions to take. This will be flushed in queue_update, so our
        # companion data stays synchronized with the Topology
        self.updates = []

        # TODO: implement mininet connectivity
        # this is constructor, but file doesn't get added until after constructor.
        # maybe check for it later?
        try:
            self.topo_file = self.runtime.topo_file
        except:
            pass
        self.mininet = False

        # Continually read from the WebSocket.
        # If the connection closes unexpectedly, try to reopen it
        # Probably overkill, as the server really shouldn't die
        def read_loop():
            while True:
                try:
                    msg = self.ws.recv()
                except: #what specific exception?
                    self.log.warn('WebSocket closed unexpectedly. Reconnecting')
                    if not self.connect():
                        self.log.error("Couldn't reestablish connection. Exiting loop")
                        break # Stop the loop, since there's nothing to read
                else:
                    self.process_message(msg)
        
        self.thread = threading.Thread(target = read_loop, name = 'read loop')
        self.thread.daemon = True
        self.thread.start()

    # Connect to the websocket forwarder. If it is down, try to restart it
    # TODO: Don't try to restart the server. It shouldn't die
    def connect(self, second_try=False):
        try:
            ws = create_connection(WS_URL)
            self.log.debug('Connected to WebSocket server')
            return ws

        except socket.error:
            if not second_try:
                start_ws_forwarder()
                return self.connect(True)
            else:
                self.log.warn("Couldn't connect to WebSocket. Is forwarding server running?")
                return None

    # Process incoming messages
    def process_message(self, msg):
        if msg == 'initialize':
            if self.mininet:
                #self.initialize_from_mininet()
                pass
            else:
                #self.initialize_from_topo(net.topology)
                if not self.curr_topo:
                    self.log.warn("No topology found. Do you have a network running?")
                else:
                    self.update_topo(self.curr_topo)
            
        else:
            self.log.warn('Unrecognized message from browser: %s' % msg)


    # Send messages out through the WebSocket
    def send_to_ws(self, msg):
        if not self.ws:
            self.log.warn('Sending failed: no WebSocket connection')
            return
        self.ws.send(msg)

    def update_topo(self, topo):
        self.curr_topo = topo
        if not self.ws:
            return

        d = json_graph.node_link_data(self.build_from(self.curr_topo))
        d['message_type'] = 'network'
        self.ws.send(json.dumps(d))

    # Override (but maybe not needed in merged class?)
    def queue_update(self,this_update_no):
        def f(this_update_no):
            time.sleep(self.wait_period)
            with self.update_no_lock:
                if this_update_no != self.update_no:
                    return

            self.topology = self.next_topo.copy()
            self.runtime.handle_network_change()
            self.update_topo(self.topology)

        p = threading.Thread(target=f,args=(this_update_no,))
        p.start()

    def handle_switch_join(self, switch, **kwargs):
        super(VisConcreteNetwork,self).handle_switch_join(switch)
        #s = Switch("Switch %d" % switch)
        #for k,v in kwargs.iteritems():
        #    setattr(s, k, v)
        #self.updates.append(("join", s))
        print 'handle switch join: %d' % switch

    def handle_switch_part(self, switch):
        super(VisConcreteNetwork,self).handle_switch_part(switch)
        print 'handle switch part: %d' % switch

    def handle_port_join(self, switch, port_no, config, status):
        super(VisConcreteNetwork,self).handle_port_join(switch, port_no, config, status)
        #print 'handle port join: %d %d %s %s' % (switch, port_no, config, status)

    def handle_port_part(self, switch, port_no):
        super(VisConcreteNetwork,self).handle_port_part(switch, port_no)
        print 'handle port part: %d %d' % (switch, port_no)

    def handle_port_mod(self, switch, port_no, config, status):
        super(VisConcreteNetwork,self).handle_port_mod(switch, port_no, config, status)
        print 'handle port mod: %d %d %s %s' % (switch, port_no, config, status)

    def port_up(self, switch, port_no):
        super(VisConcreteNetwork,self).port_up(switch, port_no)
        print 'port up: %d %d' % (switch, port_no)

    def port_down(self, switch, port_no, double_check=False):
        super(VisConcreteNetwork,self).port_down(switch, port_no, double_check)
        print 'port down: %d %d %s' % (switch, port_no, double_check)

    def handle_link_update(self, s1, p_no1, s2, p_no2):
        super(VisConcreteNetwork,self).handle_link_update(s1, p_no1, s2, p_no2)
        print 'handle link update: %d %d %d %d' % (s1, p_no1, s2, p_no2)






    # Construct a graph using our customized nodes and edges
    def build_from(self, topo):
        g = nx.Graph()
        for n in topo.node:
            g.add_node(n, name = 'Switch %s' % n, node_type = 'switch')
            for p in topo.node[n]['ports']:
                port = topo.node[n]['ports'][p]

                portname = "%s[%s]" % (n, port.port_no)
                
                if port.definitely_down(): #dead link
                    dead_link_node = '%s_X' % portname
                    g.add_node(dead_link_node, name = dead_link_node, node_type = 'dead')
                    g.add_edge(dead_link_node, n, name = "%s <--> X" % portname)

                elif port.linked_to: #link to another switch
                    link_title = '%s[%s] <--> %s' % (port.linked_to.switch, port.linked_to.port_no, portname)
                    g.add_edge(n, port.linked_to.switch, name = link_title)

                else: #egress link
                    egress_node = '%s_egress' % portname
                    g.add_node(egress_node, name = egress_node, node_type = 'egress')
                    g.add_edge(egress_node, n, name = "%s <--> Outside" % portname)
        return g

