/*TODO
1. Make split pane on the left for info and stuff
2. Keep nodes within bounds (1.5x width?)
3. Write method to handle changing properties of links/nodes
5. Ctrl-click to un-fix nodes
6. Wrap long labels
*/

var ws;
var mininet = false;
var interval = 0;
var flow_stats = {};

$('document').ready(connect);

function connect() {
    var host = window.location.hostname;
    var url = "ws://" + host + ":8181/ws"
    ws = new WebSocket(url);

    ws.onmessage = function (event) {
        console.log(event.data);
        if (event.data.match('WS')) {
            process_WS_message(event.data);
        } else {
            json = jQuery.parseJSON(event.data);
            process_message(json);
        }
    };

    ws.onopen = function () {
        d3.select("#no_ws").attr("hidden", '');
        ws.send('WS_VIEW_CLIENT');
        ws.send('current_network');
        ws.send('port_stats_request');
        ws.send('flow_stats_request');
        interval = setInterval(function() {ws.send('port_stats_request'); ws.send('flow_stats_request'); }, 5000);
    };

    ws.onclose = function () {
        d3.select("#no_ws").attr("hidden", null);
        setTimeout(connect, 5000);
        if (interval) { clearInterval(interval); }
    };
}


function process_message(json) {
    switch (json.message_type) {
        case undefined:
            console.log('WARNING: No message_type found. Discarding message');
            break;
        case 'network':
            handle_network(json);
            break;
        case 'packet':
            handle_packet(json);
            break;
        case 'port_stats_reply':
            handle_port_stats_reply(json);
            break;
        case 'flow_stats_reply':
            handle_flow_stats_reply(json);
            break;
        default:
            console.log('WARNING: Unrecognized message_type: ' + json.message_type + '. Discarding message');
            break;
    }
}

//Allow an element to be moved to the front (like when dragging a node)
d3.selection.prototype.moveToFront = function() { 
  return this.each(function() { 
      this.parentNode.appendChild(this); 
    }); 
};

link_context_options =[
    { name : 'Bring down', fn : link_down, mininet_only : true },
    { name : 'Bring up', fn : link_up, mininet_only : true },
]

node_context_options = [
    { name : 'Rename', fn : node_rename }, //Doesn't currently do anything
    { name : 'Start xterm', fn : node_xterm, mininet_only : true },
]


//Structure
var sidebar = d3.select("#sidebar");

var content = d3.select("#content");

var w, h, boxw = 100, boxh = 40;

calc();
// Deal with panning and zooming
var zoom = d3.behavior.zoom()
    .size([w,h])
    .scaleExtent([.25,2])
    .on("zoom", zoomed); 

var svg = content
    .append("svg")
    .attr("width", w)
    .attr("height", h)
    .call(zoom)
    .on("click", remove_contextmenu)
    .on("dblclick.zoom", null); //for now: disable double clicking entirely

var rect = svg.append("rect")
    .attr("id", "mousecapture")
    .attr("width", "100%")
    .attr("height", "100%");

//the <g> tag containing the whole visualization. This gets zoomed and panned
var vis = svg.append("g");

//do this so that nodes will always render on top of links
vis.append("g").attr("id", "links");
vis.append("g").attr("id", "nodes");

vis.append("g").attr("id", "contextmenu");


calc();
set_sizes();

//a flag so that we don't zoom when double clicking nodes
var _on_node = false;


//Defines what happens when dragging around nodes
var drag = d3.behavior.drag()
    .origin(function(d) { return d; })
    .on("dragstart", dragstart)
    .on("drag", dragged)
    .on("dragend", dragend);

//set the force layout to be centered in the screen
zoom.translate([w/2, h/2]);
zoom.event(vis);

var force = d3.layout.force()
    .gravity(0.01)
    .size([1,1])
    .charge(-1000)
    .chargeDistance(1000)
    .charge(function(d) {return (d.node_type == "switch") ? -800 : -1200;})
    .linkDistance(300);

// called anytime the user zooms or pans
function zoomed(d) {
    //if we got here because a node was double clicked, don't do anything
    /*if (d3.event.sourceEvent && d3.event.sourceEvent.defaultPrevented) {
        console.log('prevented');
    }
    console.log('zoomed')
    console.log(d3.event)
    if (_on_node) {
        _on_node = false;
        return;
    }*/
    //console.log(d3.event);
    remove_contextmenu();
    if (d3.event.sourceEvent && d3.event.sourceEvent.which != 1) { return; }
    trans = d3.event.translate;
    scale = d3.event.scale;
    x=trans[0];
    y=trans[1];
    x = Math.min(w, Math.max(0, x)); // bound x to the range [0,w]
    y = Math.min(h, Math.max(0, y)); // bound y to the range [0,h]

    zoom.translate([x,y]);
    vis.attr("transform", "translate(" + [x,y] + ")scale(" + scale + ")");
};

function dragstart(d) {
    console.log('dragstart');
    remove_contextmenu();
    real_drag = d3.event.sourceEvent.which == 1;
    if (!real_drag) { return; }
    d3.event.sourceEvent.stopPropagation();
    force.stop();
    d3.select(this).classed("fixed", d.fixed = true);
    d3.select(this).classed("dragging", true);
    d3.select(this).moveToFront();
};

//This is needed to make sure that the layout updates correctly while dragging.
//Just calling tick() causes problems
function dragged(d) {
    if (!real_drag) { return; }
    d.px += d3.event.dx;
    d.py += d3.event.dy;
    d.x += d3.event.dx;
    d.y += d3.event.dy;
    tick();
};

function dragend(d) {
    if (!real_drag) { return; }
    d3.select(this).classed("dragging", false);
    force.resume();
    //tick();
};

function dblclick(d) {
    /*_on_node = true;
    d3.event.preventDefault();
    console.log('bdlclick');*/
    d3.select(this).classed("fixed", d.fixed = false);
}

//These are the nodes and links which existed before the json arrived
//This allows us to keep track of the links that were already in the layout (especially their positions)
var present_nodes = [];
var present_links = [];

var link;
var node;

//when we get a new network topology, process it
function handle_network(json) {

    mininet = json.mininet;

    //Update json.links and json.nodes:
    //If a link/node is already in present_links/nodes (i.e. it was in the layout already),
    //change its entry in json.links/nodes to point to the existing object, rather than the one
    //that was created when the new JSON came in

    function update_json(json_elements, present_elements) {
        present_names = {}
        for (i = 0; i < present_elements.length; i++) {
            name = present_elements[i].name;
            present_names[name] = present_elements[i];
        }
        for (i=0; i < json_elements.length; i++) {
            name = json_elements[i].name;
            if (name in present_names) {
                $.extend(true, present_names[name], json_elements[i]);
                json_elements[i] = present_names[name];
            }
        }
    }

    update_json(json.links, present_links);
    update_json(json.nodes, present_nodes);


    linkgroup = vis.select("#links").selectAll(".linkgroup")
        .data(json.links, function(d) { return d.name;});

    linkgroup
        .select("line")
        .classed("link", true)
        .classed("up", function(d) { return d.status == 'up'; })
        .classed("down", function(d) { return d.status == 'down'; });

    linkgroup
        .exit()
        .remove()
        .each(function(d) {
            for (i = 0; i < present_links.length; i++) {
                if (present_links[i].name == d.name) {
                    present_links.splice(i, 1);
                }
            }
        });

    link = linkgroup
        .enter()
        .insert("g")
        .classed("linkgroup", true)
        .on("contextmenu", link_contextmenu)
        .each(function(d) { present_links.push(d); });
        
    link.append("svg:line")
        .classed("link", true)
        .classed("up", function(d) { return d.status == 'up'; })
        .classed("down", function(d) { return d.status == 'down'; })
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; })
        .classed("low_bandwidth", function(d) { return d.bandwidth == 'low'; })
        .classed("med_bandwidth", function(d) { return d.bandwidth == 'med'; })
        .classed("high_bandwidth", function(d) { return d.bandwidth == 'high'; });

    link.append("text")
        .text(function(d) { return d.name; })
        .attr("dy", "-.33em")
        .classed("link-name", true);
    
    link.append("text")
        .attr("dy", "1em")
        .classed("link-stats", true);

    nodegroup = vis.select("#nodes").selectAll(".nodegroup")
        .data(json.nodes, function(d) { return d.name;});
    
    nodegroup
        .exit()
        .remove()
        .each(function(d) {
            for (i = 0; i < present_nodes.length; i++) {
                if (present_nodes[i].name == d.name) {
                    present_nodes.splice(i, 1);
                }
            }
        });

    node = nodegroup
        .enter()
        .insert("g")
        .classed("nodegroup", true)
        .on("dblclick", dblclick, true)
        .on("contextmenu", node_contextmenu)
        //.on("contextmenu.drag", function() {console.log("context drag"); d3.event.sourceEvent.stopPropogation(); })
        .call(drag)
        .on("click",
                function(d,i) {
                    remove_contextmenu();
                    d3.selectAll(".selected").classed("selected", false);
                    d3.select(this).classed("selected", true);
                    populate_sidebar();
                })
        .each(function(d) { present_nodes.push(d); });

        //doubleclick: select
        //ctrl click: unfreeze

    node.append("svg:rect")
        .classed("node", true)
        .classed("switch", function(d) { return d.node_type == 'switch'; })
        .classed("host", function(d) { return d.node_type == 'host'; })
        .attr("width", boxw)
        .attr("height", boxh)
        .attr("x", -boxw / 2)
        .attr("y", -boxh / 2)
        .attr("rx", 5)
        .attr("ry", 5);

    node.append("text")
        .text(function(d) { return d.name; })
        .attr("x", function(d) { return (0); })
        .attr("y", function(d) { return (0); });

    //Very crude. Just generally gets switches to the front
    node.sort(function(a,b) {return a.node_type == "switch" ? 1 : 0;});
    
    force
        .links(json.links)
        .nodes(json.nodes)
        .on("tick", tick)
        .start();


    function dfs() {
        json.nodes.forEach(function(d) { d.seen = false; d.level = 0; });

        json.nodes.forEach(function(d, i) {
            if (d.node_type == 'host') {
                ;
            }
        });
    }
    present_node_names = {};
    for (i = 0; i < present_nodes.length; i++) {
        name = present_nodes[i].name;
        present_node_names[name] = present_nodes[i];
    }
    present_link_names = {};
    for (i = 0; i < present_links.length; i++) {
        name = present_links[i].name;
        present_link_names[name] = present_links[i];
    }

    port_map = {}; // { switch : {port : link } }
    for (i = 0; i< present_links.length; i++) {
        ln = present_links[i];
        source_dpid = ln.source.dpid;
        source_port = ln.source_port;
        target_dpid = ln.target.dpid;
        target_port = ln.target_port;

        if (!port_map[source_dpid]) { port_map[source_dpid] = {}; }
        if (!port_map[target_dpid]) { port_map[target_dpid] = {}; }
        port_map[source_dpid][source_port] = [ln, 'source'];
        port_map[target_dpid][target_port] = [ln, 'target'];
    }
}

function handle_packet(json) {
    //name = 's' + json['switch'];
    //other = present_node_names[name].ports[json['inport']];
    //console.log("packet from " + other + " to " + name);
}

function handle_port_stats_reply(json) {
    for (i = 0; i < present_links.length; i++) {
        ln = present_links[i];
        ln.packets_to_source = 0;
        ln.packets_from_source = 0;
        ln.packets_to_target = 0;
        ln.packets_from_target = 0;
    }
    for (sw_num in json.counts) {
        sw = json.counts[sw_num];
        console.log(sw);
        for (port_num in sw) {
            console.log(port_num);
            //get the link associated with this port on this switch
            this_link = port_map[sw_num][port_num][0];
            src_tgt = port_map[sw_num][port_num][1];
            pkts = sw[port_num];
            if (src_tgt == 'source') {
                this_link.packets_to_source = pkts[0];
                this_link.packets_from_source = pkts[1];
            } else if (src_tgt == 'target') {
                this_link.packets_to_target = pkts[0];
                this_link.packets_from_target = pkts[1];
            }
        }
    }
    d3.selectAll(".linkgroup").select(".link-stats")
        .text(
            function(d) {
                return 'To ' + d.source.name + ': [' + d.packets_from_target + ', ' + d.packets_to_source + 
                    '] To ' + d.target.name + ': [' + d.packets_from_source + ', ' + d.packets_to_target + ']';
            });
    d3.selectAll(".linkgroup").select(".link")
        .each(function (d) { d.avg_packets = (d.packets_from_target + d.packets_to_source + 
                    d.packets_from_source + d.packets_to_target) / 4; })
        .classed("low_util", function (d) { return d.avg_packets <= 100; })
        .classed("med_util", function (d) { return d.avg_packets > 100 && d.avg_packets <= 500; })
        .classed("high_util", function (d) { return d.avg_packets > 500; });
}

function handle_flow_stats_reply(json) {
    sw = json.switch;
    stats = json.flow_stats;
    flow_stats[sw] = stats;
    populate_sidebar();
}

function tick() {
    a=force.alpha();

    linkgroup.select("line")
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    linkgroup.selectAll("text")
        .attr("x", function(d) { return (d.source.x + d.target.x)/2;})
        .attr("y", function(d) { return (d.source.y + d.target.y)/2;})
        .attr("transform", function(d) {
            dy = d.source.y - d.target.y;
            dx = d.source.x - d.target.x;
            theta = Math.atan2(dy,dx) * 180/Math.PI;
            if (theta > 90 || theta < -90) {
                theta += 180;
            }
            return "rotate(" + theta + " " + (d.source.x + d.target.x)/2 + "," + (d.source.y + d.target.y)/2 + ")"; });

    nodegroup
        .attr("transform", function (d) { return "translate(" + d.x + ", " + d.y + ")"; });
}


function node_contextmenu(d, i) {
    x = d3.mouse(this)[0] + d.x;
    y = d3.mouse(this)[1] + d.y;
    return contextmenu(d, i, [x,y], node_context_options, this);
}

function link_contextmenu(d, i) {
    return contextmenu(d, i, d3.mouse(this), link_context_options, this);
}

function contextmenu(d, i, pos, menu_items, obj) {
    d3.event.preventDefault();
    d3.event.stopPropagation();

    force.stop();

    // Remove any other context menus
    remove_contextmenu();

    selected = d;

    x = pos[0];
    y = pos[1];

    width = 80;

    menu = d3.select("#contextmenu");

    filtered_menu_items = menu_items.filter(function (d) { return mininet || !d.mininet_only; });
    
    menu_box = menu
        .append("rect")
        .classed("context_menu_bg", true)
        .attr("x", x)
        .attr("y", y)
        .attr("height", filtered_menu_items.length + "em")
        .attr("width", width);

    menuitem = menu
        .selectAll("g")
        .data(filtered_menu_items)
        .enter()
        .append("g")
        .classed("menuitem", true);

    menuitem
        .append("text")
        .text(function (item) { return item.name; })
        .attr("x", x)
        .attr("y", y)
        .attr("dx", "2.5px")
        .attr("dy", function(d, i) { return (i+1) - 0.15 + "em"; }); // this just makes it look better
    
    menuitem.selectAll("text").each(
            function(d,i) {
                width = Math.max(d3.select(this).node().getBBox().width + 5, width);
            });

    menu_box.attr("width", width);

    menuitem
        .append("rect")
        .classed("context_item_bg", true)
        .attr("x", x)
        .attr("y", function(d,i) { return d3.select(this.parentNode).select("text").node().getBBox().y; })
        .attr("width", width)
        .attr("height", function(d,i) { return d3.select(this.parentNode).select("text").node().getBBox().height; })
        .on("mouseenter", function() { d3.select(this).classed("selected", true); })
        .on("mouseleave", function() { d3.select(this).classed("selected", false); })
        .on("click", function(d) { d.fn(selected); });

}

function remove_contextmenu() {
    d3.selectAll("#contextmenu *")
        .remove();
}

function link_down(link) {
    node1 = link.source.name;
    node2 = link.target.name;
    ws.send('link ' + node1 + ' ' + node2 + ' down');
}

function link_up(link) {
    node1 = link.source.name;
    node2 = link.target.name;
    ws.send('link ' + node1 + ' ' + node2 + ' up');
}

function node_rename(node) {
    new_name = prompt('New name');
    if (new_name) { ws.send('node rename ' + node.name + ' ' + new_name); }
}

function node_xterm(node) {
    ws.send('node xterm ' + node.name);
}

function node_selected(node) {
    ws.send('');
}

function populate_sidebar() {
    node = d3.select(".nodegroup.selected");
    if (node.empty()) {
        return;
    }
    d3.select("#nodename").text(node.datum().name);
    d3.select("#");
}

window.onresize = function () {
    calc();
    set_sizes();
}

function set_sizes() {
    svg.attr("width", w)
        .attr("height", h); 
}

function calc() {
    w = $("#content").width();
    h = $(window).height(); 
}
