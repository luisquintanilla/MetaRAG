# Description: This file contains the implementation of Knowledge Graph storage utilities of the AI Pipeline.
# Maintainers: Diego Colombo and Tara E. Walker

import json
import re
from itertools import groupby
from llama_index.core.llms.llm import LLM
from llama_index.core.base.llms.types import (
    ChatMessage,
    MessageRole
)

from aipipeline.knowledge_graph.kg_base_component import KnowledgeGraphBaseComponent

from aipipeline.knowledge_graph.unstructured_data_utils import (
    nodesTextToListOfKnowledgeGraphNodes,
    relationshipTextToListOfKnowledgeGraphRelationship,
)

def generate_system_message_for_nodes() -> str:
    return """Your task is to identify if there are duplicated nodes and if so merge them into one nod. Only merge the nodes that refer to the same entity.
You will be given different datasets of nodes and some of these nodes may be duplicated or refer to the same entity. 
The datasets contains nodes in the form [ENTITY_ID, TYPE, PROPERTIES]. When you have completed your task please give me the 
resulting nodes in the same format. Only return the nodes and relationships no other text. If there is no duplicated nodes return the original nodes.

When defining the propreties for the nodes please use wellknwon types from schema.org that match the entity TYPE.

Here is an example of the input you will be given:
["alice", "Person", {"age": 25, "occupation": "lawyer", "name":"Alice"}], ["bob", "Person", {"occupation": "journalist", "name": "Bob"}], ["alice.com", "Webpage", {"url": "www.alice.com"}], ["bob.com", "Webpage", {"url": "www.bob.com"}]
"""


def generate_system_message_for_relationships() -> str:
    return """
Your task is to identify if a set of relationships make sense.
If they do not make sense please remove them from the dataset.
Some relationships may be duplicated or refer to the same entity. 
Please merge relationships that refer to the same entity.
The datasets contains relationships in the form [ENTITY_ID_1, RELATIONSHIP, ENTITY_ID_2, PROPERTIES].
You will also be given a set of ENTITY_IDs that are valid.
Some relationships may use ENTITY_IDs that are not in the valid set but refer to a entity in the valid set.
If a relationships refer to a ENTITY_ID in the valid set please change the ID so it matches the valid ID.
When you have completed your task please give me the valid relationships in the same format. Only return the relationships no other text.

When defining the propreties for the relationships please use wellknwon types from schema.org that mathed the RELATIONSHIP type.

Here is an example of the input you will be given:
["alice", "roommate", "bob", {"start": 2021}], ["alice", "owns", "alice.com", {}], ["bob", "owns", "bob.com", {}]
"""


def generate_prompt(data) -> str:
    return f""" Here is the data:
{data}
"""

internalRegex = "\[(.*?)\]"

class DataDisambiguation(KnowledgeGraphBaseComponent):
    """
    A class used to disambiguate data nodes and relationships in a knowledge graph.
    Attributes
    ----------
    llm : LLM
        An instance of a language model used for processing and generating text.
    Methods
    -------
    run(data: dict) -> str
        Processes the input data to disambiguate nodes and relationships, returning the updated nodes and relationships.
    """
    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def run(self, data: dict) -> str:
        nodes = sorted(data["nodes"], key=lambda x: x["label"])
        relationships = data["relationships"]
        new_nodes = []
        new_relationships = []

        node_groups = groupby(nodes, lambda x: x["label"])
        for group in node_groups:
            disString = ""
            nodes_in_group = list(group[1])
            if len(nodes_in_group) == 1:
                new_nodes.extend(nodes_in_group)
                continue

            for node in nodes_in_group:
                disString += (
                    '["'
                    + node["name"]
                    + '", "'
                    + node["label"]
                    + '", '
                    + json.dumps(node["properties"])
                    + "]\n"
                )

            message = [
                ChatMessage(role= MessageRole.SYSTEM, content=generate_system_message_for_relationships()),
                ChatMessage(role= MessageRole.USER, content=disString)
            ]

            rawNodes = (self.llm.chat(message)).message.content

            n = re.findall(internalRegex, rawNodes)

            new_nodes.extend(nodesTextToListOfKnowledgeGraphNodes(n))

        relationship_data = "Relationships:\n"
        for relation in relationships:
            relationship_data += (
                '["'
                + relation["start"]
                + '", "'
                + relation["type"]
                + '", "'
                + relation["end"]
                + '", '
                + json.dumps(relation["properties"])
                + "]\n"
            )

        node_labels = [node["name"] for node in new_nodes]
        relationship_data += "Valid Nodes:\n" + "\n".join(node_labels)

        message = [
                ChatMessage(role= MessageRole.SYSTEM, content=generate_system_message_for_relationships()),
                ChatMessage(role= MessageRole.USER, content=generate_prompt(relationship_data))
            ]
        
        rawRelationships = (self.llm.chat(message)).message.content

        rels = re.findall(internalRegex, rawRelationships)
        new_relationships.extend(relationshipTextToListOfKnowledgeGraphRelationship(rels))
        return {"nodes": new_nodes, "relationships": new_relationships}