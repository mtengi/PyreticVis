#!/usr/bin/env python

from mininet.topo import Topo
from mininet.link import Link, Intf

import networkx

class GMLTopo(Topo):
    def __init__(self, filename):
        super(GMLTopo,self).__init__()
        
        g = networkx.read_gml(filename)
        for i in g.nodes():
            node = g.node[i]
            # change the name so that we don't try to give a switch MAC address 0
            # TODO: use actual name if given
            self.addNode(str(i), **node)

        for n1,n2,data in g.edges(data=True):
            self.addLink(str(n1),str(n2),**data) #add info


# A small modification of the Link class allowing us to store arbitrary data for each link
class GMLLink(Link):
    def __init__( self, node1, node2, port1=None, port2=None,
                  intfName1=None, intfName2=None,
                  intf=Intf, cls1=None, cls2=None, params1=None,
                  params2=None, **extras):
        super(GMLLink,self).__init__(node1,node2,port1,port2,intfName1,
                intfName2,intf,cls1,cls2,params1,params2)
        self.extras = extras

def main(stdin,filename):
    import sys
    import subprocess
    from mininet.net import Mininet
    from mininet.cli import CLI
    from mininet.clean import cleanup
    from mininet.node import RemoteController
    from mininet.log import lg

    # Basically emulate a call to mininet.sh:
    # Clean up, then make a network and open the CLI
    lg.setLogLevel('info')
    cleanup()
    net = Mininet(topo=GMLTopo(filename),
            controller = RemoteController,
            link=GMLLink,
            autoSetMacs=True)
    net.start()
    CLI(net)
    net.stop()
    raw_input('Press enter to exit...')

if __name__ == '__main__':
    import sys
    filename = sys.argv[1]
    main(sys.stdin, filename)
