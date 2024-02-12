from . import source as prov

from asciidag.graph import Graph
from asciidag.node import Node

SETTINGS = prov.SETTINGS

def convert_to_asciidag(G):
    """ Convert NetworkX graph to the asciidag format. """

    if SETTINGS['DEBUG']: print('===============================')
    if SETTINGS['DEBUG']: print('===== CONVERT TO ASCIIDAG =====')
    if SETTINGS['DEBUG']: print('===============================\n')

    def parents_func(G,node):
        nodes = G.predecessors(node) # return parents
        #nodes = G.successors(node) # return children
        return list(nodes)
    
    def get_parents(G,node_networkx,BUF): # recursively search for parents        
        
        if SETTINGS['DEBUG']: print('\n=== get_parents ===')
        
        parents_asciidag = []        
        parents_networkx = parents_func(G,node_networkx)
        #if SETTINGS['DEBUG']: print('parents_networkx>>>',parents_networkx)
        if SETTINGS['DEBUG']: print('parents>>>',[G.nodes[n]['label'] for n in parents_networkx])
        
        for parent_networkx in parents_networkx:
            
            label = G.nodes[parent_networkx]['label']
            if SETTINGS['DEBUG']: print('label>>>',label)
            
            hashval = parent_networkx
            if SETTINGS['DEBUG']: print('hashval>>>',hashval)
            
            if hashval in BUF:
                if SETTINGS['DEBUG']: print('hashval in BUF')
                parent_asciidag = BUF[hashval]
            else:
                if SETTINGS['DEBUG']: print('hashval NOT in BUF')
                grandparents_asciidag = get_parents(G,parent_networkx,BUF)
                parent_asciidag = Node(label,parents=grandparents_asciidag)
                BUF[hashval] = parent_asciidag
            
            parents_asciidag.append(parent_asciidag)
        
        return parents_asciidag
    
    NODES_ASCIIDAG = {}
    
    for node_networkx in G.nodes:   
        
        if SETTINGS['DEBUG']: print('===== OUTER LOOP =====\n')
             
        label = G.nodes[node_networkx]['label']  
        if SETTINGS['DEBUG']: print('label>>>',label)
        
        hashval = node_networkx
        if SETTINGS['DEBUG']: print('hashval>>>',hashval)
              
        parents_asciidag = get_parents(G,node_networkx,NODES_ASCIIDAG)        
        
        if hashval not in NODES_ASCIIDAG:            
            node_asciidag = Node(label,parents=parents_asciidag)        
            NODES_ASCIIDAG[hashval] = node_asciidag
            
    nodes = list(NODES_ASCIIDAG.values())
    
    return nodes

def show_ascii(G):
    nodes_asciidag = convert_to_asciidag(G)
    graph = Graph()
    graph.show_nodes(nodes_asciidag)
