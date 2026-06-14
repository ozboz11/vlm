from enum import Enum

from pydantic import BaseModel


class NodeType(str, Enum):
    event       = "event"
    function    = "function"
    system      = "system"
    role        = "role"
    risk        = "risk"
    information = "information"
    gateway     = "gateway"


class EdgeType(str, Enum):
    sequence = "sequence"   # process flow
    performs = "performs"   # role → function
    supports = "supports"   # system → function
    produces = "produces"   # function → information
    uses     = "uses"       # information → function


class Node(BaseModel):
    label:     str
    node_type: NodeType = NodeType.function


class Edge(BaseModel):
    from_label: str
    to_label:   str
    edge_label: str      = ""
    edge_type:  EdgeType = EdgeType.sequence


class SchemaGraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
