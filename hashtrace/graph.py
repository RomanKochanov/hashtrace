import sys
import json

import pylab as pl

import numpy as np
import networkx as nx

from . import source as prov


# =======================================
# PLOTTING
# =======================================

# crop large lists and dicts:
# https://stackoverflow.com/questions/38533282/python-pretty-print-dictionary-of-lists-abbreviate-long-lists

from pprint import PrettyPrinter

class CroppingPrettyPrinter(PrettyPrinter):

    def __init__(self, *args, **kwargs):
        self.maxlist = kwargs.pop('maxlist', 6)
        self.maxdict = kwargs.pop('maxdict', 6)
        return PrettyPrinter.__init__(self, *args, **kwargs)

    def _format(self, obj, stream, indent, allowance, context, level):
        if isinstance(obj, list):
            # If object is a list, crop a copy of it according to self.maxlist
            # and append an ellipsis
            if len(obj) > self.maxlist:
                #cropped_obj = obj[:self.maxlist] + ['...']
                cropped_obj = '[%d items]'%len(obj)
                return PrettyPrinter._format(
                    self, cropped_obj, stream, indent,
                    allowance, context, level)

        if isinstance(obj, dict):
            # If object is a dict, make a simple stub
            if len(obj) > self.maxdict:
                #stub_obj = 'long dict (%d items)'%len(obj)
                stub_obj = '{%d items}'%len(obj)
                return PrettyPrinter._format(
                    self, stub_obj, stream, indent,
                    allowance, context, level)

        if isinstance(obj, np.ndarray):
            # If object is a Numpy array, output dimension
            if True:
                stub_obj = 'np.ndarray(%s)'%str(obj.shape)
                return PrettyPrinter._format(
                    self, stub_obj, stream, indent,
                    allowance, context, level)


        # Let the original implementation handle anything else
        # Note: No use of super() because PrettyPrinter is an old-style class
        return PrettyPrinter._format(
            self, obj, stream, indent, allowance, context, level)

pos_funcs = {
    'planar': nx.planar_layout,
    'kamada_kawai': nx.kamada_kawai_layout,
    'spiral': nx.spiral_layout,
    'shell': nx.shell_layout,
    'spectral': nx.spectral_layout,
    'spring': nx.spring_layout,
    'circular': nx.circular_layout,
    'random': nx.random_layout,
    'bipartite': nx.bipartite_layout,
    'multipartite': nx.multipartite_layout,
    'rescale': nx.rescale_layout,
    'rescale_dict': nx.rescale_layout_dict,
}

def add_node(G,container,label,color='blue'):
    shape = 'o'
    G.add_nodes_from([
        (container.__hashval__,
        {'classname':container.__classname__,'shape':shape,'label':label,'color':color}),
    ])

def add_edge(G,container_from,container_to,color,weight):
    G.add_edge(container_from.__hashval__,container_to.__hashval__,
        color=color,weight=weight)

def get_function_name(container):
    buf = json.loads(container.__buffer__) # will not always work
    return buf['name']

def build_graph(db_backend=prov.db_backend):
    
    """ build graph """
    
    workflows = db_backend.select(where='contained_class=="Workflow"')
    for item in workflows.getitems():
        item['container_workflow'] = prov.Container.search(item['hashval'])
   
    p = CroppingPrettyPrinter(maxlist=6,maxdict=4)

    # Create empty graph.
    G = nx.DiGraph()

    # Fill graph with nodes and edges.
    for item in workflows.getitems():
            
        # Get workflow object from item.
        container_workflow = item['container_workflow']
        workflow = container_workflow.object
        
        # save function node
        container_function = workflow.function
        color = 'magenta'
        add_node(G,container_workflow,label=get_function_name(container_function),color=color)
        #add_node(G,container_workflow,label=container_function.pretty_print(),color=color)
        
        # save args input nodes and edges
        containers_args = workflow.args        
        for i,container_arg in enumerate(containers_args):
            color = 'green'
            add_node(G,container_arg,label=p.pformat(container_arg.object),color=color)
            #add_node(G,container_arg,label=container_arg.pretty_print(),color=color)
            add_edge(G,container_arg,container_workflow,color=color,weight=1)        

        # save kwargs input nodes and edges
        containers_kwargs = workflow.kwargs
        for argname in containers_kwargs:
            color='blue'
            container_kwarg = containers_kwargs[argname]
            add_node(G,container_kwarg,label=p.pformat(container_kwarg.object),color=color)
            #add_node(G,container_kwarg,label=container_kwarg.pretty_print(),color=color)
            add_edge(G,container_kwarg,container_workflow,color=color,weight=1) 
        
        # save output nodes and edges
        coutainers_outputs = workflow.outputs
        for i,container_output in enumerate(coutainers_outputs):
            color='red'
            add_node(G,container_output,label=p.pformat(container_output.object),color=color)
            #add_node(G,container_output,label=container_output.pretty_print(),color=color)
            add_edge(G,container_workflow,container_output,color=color,weight=1)
            
    return G

def save_tgf(G,filename):
    
    """ save graph in TGF format """
    
    BUF = ''
    
    for node in G.nodes:
        BUF += '%s %s\n'%(node,G.nodes[node]['label'])
        
    BUF += '#\n'
    
    for edge in G.edges:
        BUF += '%s %s\n'%edge
        
    with open(filename,'w') as f:
        f.write(BUF)
    
    print('Graph saved to',filename)

def plot_graph(G,layout='kamada_kawai'):
        
    """ Layouts:
            planar
            kamada_kawai
            spiral
            shell
            spectral
            spring
            circular
            random
            bipartite
            multipartite
            rescale_layout
            rescale_dict
    """
            
    # DRAW GRAPH

    pos = pos_funcs[layout](G)
    
    node_labels = {key:G.nodes[key]['label'] for key in G.nodes}
    #node_labels = {key:key[:4] for key in G.nodes}

    color_map = [G.nodes[key]['color'] for key in G.nodes]

    node_shapes = [G.nodes[key]['shape'] for key in G.nodes]

    color_edges = [G[u][v]['color'] for u,v in G.edges]

    weight_edges = [G[u][v]['weight'] for u,v in G.edges]

    #print('quitting')
    #sys.exit()

    nx.draw_networkx(
        G,
        pos,
        node_size=100,
        with_labels=False,
        node_color=color_map,
        #node_shape=node_shapes,
        edge_color=color_edges,
        width=weight_edges
    )

    # DRAW LABELS
    if True:
        nx.draw_networkx_labels(
            G,pos,
            node_labels,
            font_size=20,
            font_color='black'
        )

    #print('G>>>',G)
    #print('G.nodes>>>',G.nodes)
    #print('G.edges>>>',G.edges)

    pl.show()
            
    return G
