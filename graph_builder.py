"""Convert a SchemaGraph to a NetworkX DiGraph."""

import networkx as nx
from models import SchemaGraph


def to_digraph(schema: SchemaGraph) -> nx.DiGraph:
    G = nx.DiGraph()
    for n in schema.nodes:
        G.add_node(n.label)
    for e in schema.edges:
        G.add_edge(e.from_label, e.to_label, label=e.edge_label)
    return G
