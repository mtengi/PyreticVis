/*TODO
1. Right click menu
2. Keep nodes within bounds (1.5x width?)
3. Write method to handle changing properties of links/nodes
4. Differentiate links/nodes by something other than name (like a unique id)
5. Ctrl-click to un-fix nodes
6. Wrap long labels
*/

var ws;

$('document').ready(function() {
    var host = window.location.hostname;
    var url = "ws://" + host + ":8181/ws"
    ws = new WebSocket(url);

    ws.onmessage = function (event) {
        console.log(event.data);
        json = jQuery.parseJSON(event.data);
        process_message(json)
    };

    ws.onopen = get_current_state
});

function get_current_state() {
    ws.send('current_network');
}

function process_message(json) {
    switch (json.message_type) {
        case undefined:
            console.log('WARNING: No message_type found. Discarding message');
            break;
        case 'network':
            network(json);
            break;
        case 'update':
            update(json);
            break;
        default:
            console.log('WARNING: Unrecognized message_type: ' + json.message_type + '. Discarding message');
            break;
    }
}

// Allow the content to fill the window with no scrollbars or borders
$("body").attr("style", "overflow: hidden; margin: 0px; display: flex");

//Allow an element to be moved to the front (like when dragging a node)
d3.selection.prototype.moveToFront = function() { 
  return this.each(function() { 
      this.parentNode.appendChild(this); 
    }); 
};

var w, h, boxw, boxh;

calc();

//a flag so that we don't zoom when double clicking nodes
var _on_node = false;

// Deal with panning and zooming
var zoom = d3.behavior.zoom()
    .size([w,h])
    .scaleExtent([.25,2])
    .on("zoom", zoomed); 

//Defines what happens when dragging around nodes
var drag = d3.behavior.drag()
    .origin(function(d) { return d; })
    .on("dragstart", dragstart)
    .on("drag", dragged)
    .on("dragend", dragend);

var svg = d3.select("body").append("svg")
    .attr("width", w)
    .attr("height", h)
    .call(zoom)
    .on("dblclick.zoom", null); //for now: disable double clicking entirely


var rect = svg.append("rect")
    .attr("width", w)
    .attr("height", h)
    .style("fill", "none")
    .style("pointer-events", "all");

//the <g> tag containing the whole visualization. This gets zoomed and panned
var vis = svg.append("g");

//do this so that nodes will always render on top of links
vis.append("g").attr("id", "links");
vis.append("g").attr("id", "nodes");

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
    if (_on_node) {
        _on_node = false;
        return;
    }
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
    d3.event.sourceEvent.stopPropagation();
    force.stop();
    d3.select(this).classed("fixed", d.fixed = true);
    d3.select(this).classed("dragging", true);
    d3.select(this).moveToFront();
};

//This is needed to make sure that the layout updates correctly while dragging.
//Just calling tick() causes problems
function dragged(d) {
    d.px += d3.event.dx;
    d.py += d3.event.dy;
    d.x += d3.event.dx;
    d.y += d3.event.dy;
    tick();
    
    //addition: if node is dragged off screen, call zoom.translate; zoom.event
};

function dragend(d) {
    d3.select(this).classed("dragging", false);
    force.resume();
    tick();
};

function dblclick(d) {
    _on_node = true;
    d3.event.preventDefault();
    d3.select(this).classed("fixed", d.fixed = false);
}

//These are the nodes and links which existed before the json arrived
//This allows us to keep track of the links that were already in the layout (especially their positions)
var existing_nodes = [];
var existing_links = [];

//when we get a new network topology, process it
function network(json) {

    //Update json.links and json.nodes:
    //If a link/node is already in existing_links/nodes (i.e. it was in the layout already),
    //change its entry in json.links/nodes to point to the existing object, rather than the one
    //that was created when the new JSON came in

    //Currently differentiates objects by name, but this should probably change

    function copy_d3_props(from, to) {
        to.index = from.index;
        to.x = from.x;
        to.y = from.y;
        to.px = from.px;
        to.py = from.py;
        to.fixed = from.fixed;
        to.weight = from.weight;
    }

    function copy_not_d3_props(from, to) {
        for (prop in from) {
            to[prop] = from[prop];
        }
    }

    ex_link_ids = Object();
    existing_links.forEach(
        function(val, ind) {
            ex_link_ids[val.id] = val;
        }
    );

    for (i = 0; i < json.links.length; i++) {
        id = json.links[i].id;
        if (id in ex_link_ids) {
            copy_not_d3_props(json.links[i], ex_link_ids[id]);
            json.links[i] = ex_link_ids[id];
            //copy_d3_props(ex_link_ids[id], json.links[i]);
        }
    }
    
    ex_node_ids = Object();
    existing_nodes.forEach(
        function(val, ind) {
            ex_node_ids[val.id] = val;
        }
    );

    for (i = 0; i < json.nodes.length; i++) {
        id = json.nodes[i].id;
        if (id in ex_node_ids) {
            copy_not_d3_props(json.nodes[i], ex_node_ids[id]);
            json.nodes[i] = ex_node_ids[id];
            //copy_d3_props(ex_node_ids[id], json.nodes[i]);
        }
    }

    linkgroup = vis.select("#links").selectAll(".linkgroup")
        .data(json.links, function(d) { return d.id;});

    linkgroup
        .select("line")
        .attr("class", function(d) { return "link " + d.status; });

    linkgroup
        .exit()
        .remove()
        .each(function(d) {
            for (i = 0; i < existing_links.length; i++) {
                if (existing_links[i].id == d.id) {
                    existing_links.splice(i, 1);
                }
            }
        });

    link = linkgroup
        .enter()
        .insert("g")
        .attr("class", "linkgroup")
        .each(function(d) { existing_links.push(d); });
        
    link.append("svg:line")
        .attr("class", function(d) { return "link " + d.status; })
        .style("stroke-width", 5)
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    link.append("text")
        .text(function(d) { return d.name; });

    nodegroup = vis.select("#nodes").selectAll(".nodegroup")
        .data(json.nodes, function(d) { return d.id;});
    
    nodegroup
        .exit()
        .remove()
        .each(function(d) {
            for (i = 0; i < existing_nodes.length; i++) {
                if (existing_nodes[i].id == d.id) {
                    existing_nodes.splice(i, 1);
                }
            }
        });

    node = nodegroup
        .enter()
        .insert("g")
        .attr("class", "nodegroup")
        .on("dblclick", dblclick, true)
        /*.on("contextmenu", function(data, index)  {
            console.log("context click! Data: " + data + " index: "+index);
            d3.event.preventDefault();
            d3.event.sourceEvent.stopPropogation();
        })*/
        //.on("contextmenu.drag", function() {console.log("context drag"); d3.event.sourceEvent.stopPropogation(); })
        .call(drag)
        .each(function(d) { existing_nodes.push(d); });

    node.append("svg:rect")
        .attr("class", function(d) { return "node " + d.node_type; })
        .attr("width", boxw)
        .attr("height", boxh)
        .attr("x", -boxw / 2)
        .attr("y", -boxh / 2)
        .attr("rx", 5)
        .attr("ry", 5)
        .style("cursor", "move")

    node.append("text")
        .text(function(d) { return d.name; })
        .style("text-anchor", "middle")
        .style("dominant-baseline", "middle")
        .style("cursor", "move")
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
}

function update(json) {
    update_type = json['update_type'];
    switch(json.update_type) {
        case undefined:
            console.log('update_type undefined. What are you updating?');
            break;
        case 'node':
            break;
    }

}

function tick() {
    //k = 60 * e.alpha;

    /*node.forEach(function(d, i) {
        d.y += d.node_type === "switch" ? k : -k;
    });*/

    a=force.alpha();

    json.links.forEach(function(d,i) {
        //d.source.y -= 10 * a;
        //d.target.y += 10 * a;
    });

    linkgroup.select("line")
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    linkgroup.select("text")
        .style("text-anchor", "middle")
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

window.onresize = function () {
    calc();
    
    svg.attr("width", w)
        .attr("height", h);
    
    rect.attr("width", w)
        .attr("height", h);
}

function calc() {
    w = $(window).width(),
      h = $(window).height(), 
      boxw = 100,
      boxh = 40;
}
