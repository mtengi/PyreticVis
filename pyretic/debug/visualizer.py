import networkx as nx
import json
from networkx.readwrite import json_graph
from websocket import create_connection
import socket
import threading
import logging
import time
import re
from pyretic.debug.wsforwarder import *
from mininet.term import makeTerms
from pyretic.lib.corelib import *
from pyretic.lib.std import *
from pyretic.lib.query import *
from pprint import pprint

WS_URL = 'ws://localhost:%d%s' % (WS_PORT, WS_PATH)


class VisCountBucket(CountBucket):
    def handle_flow_stats_reply(self, switch, flow_stats_reply):
        print 'FSR for %s' % switch
        pprint(flow_stats_reply)

    def register_vcn(self, vcn):
        self.vcn = vcn
        vcn.cb = self


#TODO: can this nonsense be replaced with GMLTopo and GMLLink?
class Link(object):
    def __init__(self, net, node1, port1, node2, port2, status = 'up', name =
            None, uid = None, **props):
        
        self.props = props
        self.set_prop('id', uid or id(self))
        self.set_prop('status', status)
        name = name or '%s[%s] <--> %s[%s]' % (node1, port1, node2, port2)
        self.set_prop('name', name)

        # The ends of the Link. Has the form [(Node, port)]
        self.ends = []

        self._link_to(node1, port1)
        self._link_to(node2, port2)

        self.net = net
        self.net.links[self.get_prop('id')] = self
        self.net.ports.setdefault(node1, {})
        self.net.ports.setdefault(node2, {})
        self.net.ports[node1][port1] = node2
        self.net.ports[node2][port2] = node1

    def up(self):
        self.set_prop('status', 'up')

    def down(self):
        self.set_prop('status', 'down')

    def is_up(self):
        return self.get_prop('status') == 'up'

    def set_prop(self, prop, value):
        self.props[prop] = value

    def get_prop(self, prop):
        return self.props.get(prop)

    def get_props(self):
        return self.props.copy()

    # Connect this Link to a Node at the given port.
    # If there is already a link at that port, mark it as down
    # If it is already down (i.e. the other end was disconnected), 
    def _link_to(self, node, port):
        if len(self.ends) >= 2:
            return None # Can't have a 3-way connection
        
        self.ends.append((node, port))

        # If there is already a link at the given port, remove it from both ends
        # because it no longer exists
        existing_link = node and node.get_port(port)
        if existing_link:
            existing_link.unlink_self()

        node and node.set_port(port, self)

    # Remove this Link from both of its Nodes (presumably because it was replaced
    # at one end and and you can assume that the physical link is no longer there)
    def unlink_self(self):
        for node, port in self.ends:
            node and node.set_port(port, None)

        try:
            self.net.links.pop(self.get_prop('id'))
        except KeyError:
            pass

    def __repr__(self):
        return self.get_prop('name')

    def __str__(self):
        return repr(self)


class Node(object):
    host_num = 0
    @classmethod
    def next_host_num(cls):
        cls.host_num += 1
        return cls.host_num

    def __init__(self, net, name = None, node_type = 'switch', uid = None, **props):
        self.props = props
        self.set_prop('id', uid or id(self))
        self.set_prop('node_type', node_type)
        name = name or '%s %s' %(node_type, self.get_prop('id'))
        self.set_prop('name', name)

        # A dictionary of the form { port_no : Link }
        self.ports = {}

        self.net = net
        self.net.nodes[self.get_prop('id')] = self

    def remove_self(self):
        for port, link in self.ports.copy().iteritems():
            link.unlink_self()

        try:
            self.net.nodes.pop(self.get_prop('id'))
        except KeyError:
            pass

    # Attach a link to a port. If link is None, remove the link attached to that port
    def set_port(self, port_no, link = None):
        if link == None:
            self.ports.pop(port_no)
            # If we're no longer connected to anything, remove ourself
            # This is probably not the right thing to do. What if we want isolated node?
            if len(self.ports) == 0 and self.is_host():
                self.remove_self()
        else:
            self.ports[port_no] = link

    # This is a rather roundabout method.
    # If port goes down, this is called, which calls unlink_self, which calls set_port
    # This should probablty be cleaned up and done in a more straightforward way
    def port_part(self, port_no):
        try:
            self.ports[port_no].unlink_self()
        except KeyError:
            pass

    # Get the Link connected to this Node at the given port. If nothing connected
    # there, return None
    def get_port(self, port_no):
        return self.ports.get(port_no)

    def port_up(self, port):
        try:
            self.ports[port].up()
        except KeyError:
            pass

    def port_down(self, port):
        try:
            self.ports[port].down()
        except KeyError:
            pass

    def set_prop(self, prop, value):
        self.props[prop] = value

    def get_prop(self, prop):
        return self.props.get(prop)

    def get_props(self):
        return self.props.copy()

    def is_host(self):
        return self.get_prop('node_type') == 'host'

    def __repr__(self):
        return self.get_prop('name')

    def __str__(self):
        return repr(self)

# Nodes and Links add themselves to the Network upon their creation
# Nonexistant links also remove themselves upon destruction
class Network(object):
    def __init__(self, **props):
        # Have the form { uid : Node }
        self.nodes = {}
        self.links = {}

        self.props = props

        # ports[n1][port] is n2 connected to n1's port
        self.ports = {}

    def copy(self):
        new = Network(**self.props.copy())
        new.nodes = self.nodes.copy()
        new.links = self.links.copy()
        return new

    def get_node(self, uid):
        return self.nodes.get(uid)

    def get_link(self, uid):
        return self.links.get(uid)

    def set_prop(self, prop, value):
        self.props[prop] = value

    def get_prop(self, prop):
        return self.props.get(prop)

    # Convert our network into node-link representation
    def to_node_link(self):
        nodes = [node for node in self.nodes.values()]

        # Each node needs an index 
        nodes_with_indices = {}
        for index, node in enumerate(nodes):
            nodes_with_indices[node] = index

        links = []
        for link in self.links.values():
            link_dict = link.get_props()
            source, target = [node for node,port in link.ends]
            try:
                link_dict['source'] = nodes_with_indices[source]
                link_dict['target'] = nodes_with_indices[target]
                links.append(link_dict)
            except:
                print "either source %s or target %s doesn't exist" % (source, target)

        graph = vars(self)
        graph = [] # for now. Not sure how to format in node-link

        return {'links': links, 'nodes': [node.get_props() for node in nodes], 'graph': graph}

    def to_nx_graph(self):
        return json_graph.node_link_graph(self.to_node_link(), multigraph = False)


from pyretic.core.runtime import ConcreteNetwork

##actually use this
# maybe take CN class and store it here, so we can have the superclass distinct from runtime.ConcreteNetwork
# problem is that it looks for the superclass at the time of initialization. by that point, VCN is its own superclass

# slightly more modular: if this is second recursive call to VCN.__init__, directly call Network.__init__. That would stop infinite recursion and not need to paste entire CN.__init__ here

#newest idea: merge visualizer functionality into this class. this will just make everything easier


# TODO: instead of doing try/except in all of the Network stuff, use
# next_network type scheme changes are added to the upcoming network, and then
# something in queue_update transitions the network. Not sure on the details...
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

        self.mininet = None

        self.net = Network(option1 = True)
        self.next_net = self.net.copy()

        self.network_lock = threading.Lock()

        # Keep track of how many packets we see on each port of each node
        self.packet_counts = {}


        # Continually read from the WebSocket.
        # TODO: figure out a better way to deal with forwarding server stopping
        # can try to restart it, but when?
        def read_loop():
            while True:
                try:
                    msg = self.ws.recv()
                except: #what specific exception?
                    self.log.warn('WebSocket closed unexpectedly. Stopping visualizer.')
                    break # Stop the loop, since there's nothing to read
                else:
                    self.process_message(msg)

        self.thread = threading.Thread(target = read_loop, name = 'read loop')
        self.thread.daemon = True
        self.thread.start()

    # If pyreticVis.py was called with the -t switch, this will let us interact with the Mininet instance
    def register_mininet(self, net):
        self.mininet = net

    # Shut down cleanly
    def stop(self):
        if self.mininet:
            print "stopping Mininet"
            self.mininet.stop()

    # Connect to the websocket forwarder
    def connect(self):
        try:
            ws = create_connection(WS_URL)
            self.log.debug('Connected to WebSocket forwarding server')
            return ws

        except socket.error:
            self.log.warn("Couldn't connect to WebSocket forwarding server. Is it running?")
            return None

    # Process incoming messages
    # TODO: break this out into a dictionary where the key is the string (or
    # start of the string) and the value is the function to run, given the
    # entire msg
    def process_message(self, msg):
        if msg == 'current_network':
            self.send_network()
        elif msg.startswith('link '):
            self.mininet.configLinkStatus( *msg.split()[1:] )
        elif msg.startswith('node xterm'):
            node = self.mininet[msg.split()[-1]]
            self.mininet.terms += makeTerms([node], term = 'xterm')
        elif msg == 'port_stats_request':
            self.handle_port_stats_request()
        else:
            self.log.warn('Unrecognized message from browser: %s' % msg)


    # Send messages out through the WebSocket
    def send_to_ws(self, msg):
        if not self.ws:
            self.log.warn('Sending failed: no WebSocket connection')
            return
        self.ws.send(msg)

    def send_network(self):
        if self.mininet:
            d = json_graph.node_link_data(self.mininet_to_nx_graph())
        else:
            d = json_graph.node_link_data(self.net.to_nx_graph())
        d['message_type'] = 'network'
        d['mininet'] = bool(self.mininet)
        self.send_to_ws(json.dumps(d))


    def handle_pkt(self, pkt):
        sw = pkt.header['switch']
        inport = pkt.header['inport']
        evald = self.orig_policy.eval(pkt)
        outports = [p.header['outport'] for p in evald]

        self.packet_counts.setdefault(sw, {})
        self.packet_counts[sw].setdefault(inport, [0,0]) # [pkts in, pkts out]
        self.packet_counts[sw][inport][0] += 1
        for outport in outports:
            self.packet_counts[sw].setdefault(outport, [0,0])
            self.packet_counts[sw][outport][1] += 1

        pkt_info = {}
        pkt_info['switch'] = pkt.header['switch']
        pkt_info['inport'] = pkt.header['inport']
        pkt_info['outports'] = outports
        pkt_info['message_type'] = 'packet'

        #info = {k:repr(v) for k,v in pkt.header.iteritems() if not k == 'raw'}
        #info = {'switch': repr(pkt.header['switch']), 'port': repr(pkt.header['port'])}
        #info['message_type'] = 'packet'

        # determine which link (since frontend doesn't know about ports. Should it?
        #self.send_to_ws(json.dumps(pkt_info))

    def handle_port_stats_request(self):
        reply = {'message_type': 'port_stats_reply'}
        reply['counts'] = self.packet_counts
        self.send_to_ws(json.dumps(reply))
        self.packet_counts = {}
        print 'pulling stats'
        self.cb.pull_stats()
        self.runtime.pull_stats_for_bucket(self.cb)()

    # This should be used to transition to next network
    # Also has to push changes to browser
    def queue_update(self,this_update_no):
        def f(this_update_no):
            time.sleep(self.wait_period)
            with self.update_no_lock:
                if this_update_no != self.update_no:
                    return

            self.topology = self.next_topo.copy()
            self.runtime.handle_network_change()
            self.handle_network_change()
            self.send_network()

        p = threading.Thread(target=f,args=(this_update_no,))
        p.start()


# Override methods from ConcreteNetwork
# Still need some work on what methods do exactly what
# Problem: Can't currently bring up a link to a host because port_up and handle_port_join are called
# When network is initialized, handle_port_join is called, and this makes the host node

#TODO: deal with deleting fake hosts better

    # Make a new Node
    def handle_switch_join(self, switch, **kwargs):
        super(VisConcreteNetwork,self).handle_switch_join(switch)
        print 'handle switch join: %d' % switch

        Node(self.net, uid = switch)

    def handle_switch_part(self, switch):
        super(VisConcreteNetwork,self).handle_switch_part(switch)
        print 'handle switch part: %d' % switch

        self.net.get_node(switch).remove_self()

    # When a port comes up, we can assume that it's connected to a host (not
    # tracked by Pyretic)
    # TODO: figure out how to get mininet's host number (probably related to order brought up)
    def handle_port_join(self, switch, port_no, config, status):
        super(VisConcreteNetwork,self).handle_port_join(switch, port_no, config, status)
        print 'handle port join: %d %d %s %s' % (switch, port_no, config, status)

        node1 = Node(self.net, node_type = 'host')
        node2 = self.net.get_node(switch)
        Link(self.net, node1, 0, node2, port_no)

    def handle_port_part(self, switch, port_no):
        super(VisConcreteNetwork,self).handle_port_part(switch, port_no)
        print 'handle port part: %d %d' % (switch, port_no)

        self.net.get_node(switch).port_part(port_no)

    # This is called when bringing ports up and down. Use this for host up/down
    def handle_port_mod(self, switch, port_no, config, status):
        super(VisConcreteNetwork,self).handle_port_mod(switch, port_no, config, status)
        print 'handle port mod: %d %d %s %s' % (switch, port_no, config, status)

        if config and status:
            try:
                node = self.net.get_node(switch)
                link = node.get_port(port_no)
                link.up()
            except: # link doesn't exist yet
                pass

    def port_up(self, switch, port_no):
        super(VisConcreteNetwork,self).port_up(switch, port_no)
        print 'port up: %d %d' % (switch, port_no)

    # Called when bringing link down
    def port_down(self, switch, port_no, double_check=False):
        super(VisConcreteNetwork,self).port_down(switch, port_no, double_check)
        print 'port down: %d %d %s' % (switch, port_no, double_check)

        if not double_check:
            self.net.get_node(switch).port_down(port_no)

    # Called when a link comes up between two switches. Delete the assumed hosts (TODO actually implement deletion)
    def handle_link_update(self, s1, p_no1, s2, p_no2):
        super(VisConcreteNetwork,self).handle_link_update(s1, p_no1, s2, p_no2)
        print 'handle link update: %d %d %d %d' % (s1, p_no1, s2, p_no2)

        # This doesn't do anything since these will never be hosts
        if self.net.get_node(s1) and self.net.get_node(s1).is_host():
            self.net.get_node(s1).remove_self()
        
        if self.net.get_node(s2) and self.net.get_node(s2).is_host():
            self.net.get_node(s2).remove_self()
        Link(self.net, self.net.get_node(s1), p_no1, self.net.get_node(s2), p_no2)

    # Figure out what's changed since the last update
    # Probably need locks and stuff
    def handle_network_change(self):
        with self.network_lock:
            #self.net = self.next_net
            self.next_net = self.net.copy()


    def mininet_to_nx_graph(self):
        if not self.mininet:
            return

        topo = self.mininet.topo
        mn = self.mininet

        def to_node_link():
            graph = []

            nodes = topo.nodes()
            
            # Each node needs an index 
            nodes_with_indices = {}
            for index, node in enumerate(nodes):
                nodes_with_indices[node] = index

            links = []
            for link in topo.links():
                link_dict = topo.linkInfo(*link)
                link_dict['source'] = nodes_with_indices[link[0]]
                link_dict['target'] = nodes_with_indices[link[1]]
                ports = topo.port(*link)
                link_dict['source_port'] = ports[0]
                link_dict['target_port'] = ports[1]
                src_intf = mn.link.intfName(mn.get(link[0]), ports[0])
                dst_intf = mn.link.intfName(mn.get(link[1]), ports[1])
                link_dict['status'] = 'up' if \
                            (mn.get(link[0]).intfIsUp(src_intf)
                            and mn.get(link[1]).intfIsUp(dst_intf)) else 'down'
                link_dict['name'] = '%s:%s' % (src_intf, dst_intf)
                links.append(link_dict)

            nodes_with_info = []
            for node in nodes:
                node_dict = topo.nodeInfo(node)
                node_dict['node_type'] = 'switch' if topo.isSwitch(node) else 'host'
                node_dict['name'] = node
                node_dict['ports'] = {v:k for k,v in topo.ports[node].iteritems()} # only gets first letter of k when not iteritems. weird...
                nodes_with_info.append(node_dict)

            return {'links': links, 'nodes': nodes_with_info, 'graph': graph}

        return json_graph.node_link_graph(to_node_link(), multigraph = False, directed=True)
