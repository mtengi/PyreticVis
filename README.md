pyreticVis.py - Adding a visualization to Pyretic

How it works:
pyreticVis.py replaces pyretic.py and adds a component to Pyretic's backend
which allows interactivity with thenetwork through a visualization in a web
browser. It also allows a GML topology file to be specified, and will create a
mininet network based on the specified topology.


Running:
Running pyreticVis.py is very similar to running pyretic.py. There is one
additional optional argument: -t TOPO_FILE or --topo_file=TOPO_FILE, where
TOPO_FILE is a GML file (like those available at http://topology-zoo.org). This
will launch mininet.sh in a new xterm and will build the network as specified in
the file. If you do not use this option, you will have to run mininet.sh
separately.
You also need a simple server serving up the webpage which runs the
visualization. I usually use:
$ python -m SimpleHTTPServer
in the project's root folder, which uses port 8000. My mininet VM is at
192.168.56.101 on a host-only network, so in my host OS I point Chrome to
http://192.168.56.101:8000/force/force.html. Note that you must refresh this
webpage after running pyreticVis.py, since pyreticVis.py initiates the
communication channel with the browser.


Dependencies:
websocket-client (https://github.com/liris/websocket-client)
tornado (http://www.tornadoweb.org/en/stable/)
