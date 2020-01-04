#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from six import iteritems, python_2_unicode_compatible
from builtins import str as text

from elasticsearch import Elasticsearch

from pandagg.base.interactive.mapping import as_mapping
from pandagg.base.node.query.abstract import CompoundClause, ParameterClause
from pandagg.base.node.query.abstract import QueryClause
from pandagg.base._tree import Tree


@python_2_unicode_compatible
class Query(Tree):
    """Tree combination of query nodes.

    Mapping declaration is optional, but doing so validates query validity.
    """

    node_class = QueryClause
    _crafted_root_name = 'root'

    def __init__(self, from_=None, mapping=None, identifier=None):
        # set mapping
        self.tree_mapping = None
        if mapping is not None:
            self.set_mapping(mapping)

        from_tree = None
        from_query_node = None
        from_dict = None
        if isinstance(from_, Query):
            from_tree = from_
        super(Query, self).__init__(tree=from_tree, identifier=identifier)
        if isinstance(from_, QueryClause):
            from_query_node = from_
        if isinstance(from_, dict):
            from_dict = from_
        if from_dict:
            self._build_tree_from_dict(from_dict)
        if from_query_node:
            self._build_tree_from_node(from_query_node)

    def _clone(self, identifier=None, with_tree=False, deep=False):
        return Query(
            mapping=self.tree_mapping,
            identifier=identifier,
            from_=self if with_tree else None
        )

    def set_mapping(self, mapping):
        self.tree_mapping = as_mapping(mapping)
        return self

    def _build_tree_from_dict(self, body, pid=None):
        if not isinstance(body, dict):
            raise ValueError()
        assert len(body.keys()) == 1
        q_type, q_body = next(iteritems(body))
        node = self._node_from_dict(q_type=q_type, q_body=q_body)
        self.add_node(node, pid)
        # extract children
        for child in []:
            self._build_tree_from_dict(child, node.identifier)

    def _build_tree_from_node(self, query_node, pid=None):
        # TODO accept dict syntax under class node
        self.add_node(query_node, pid)
        if isinstance(query_node, (CompoundClause, ParameterClause)):
            for child_q_node in query_node.children or []:
                self._build_tree_from_node(child_q_node, pid=query_node.identifier)
            # reset children to None to avoid confusion since this serves only __init__ syntax.
            query_node.children = None

    def add_node(self, node, pid=None):
        # TODO, validate consistency
        assert isinstance(node, QueryClause)
        super(Query, self).add_node(node, pid)

    def query_dict(self, from_=None, depth=None, with_name=True):
        if self.root is None:
            return {}
        from_ = self.root if from_ is None else from_
        node = self[from_]
        children_queries = {}
        if depth is None or depth > 0:
            if depth is not None:
                depth -= 1
            for child_node in self.children(node.name):
                children_queries[child_node.name] = self.query_dict(
                    from_=child_node.name, depth=depth, with_name=False)
        node_query_dict = node.query_dict()
        if children_queries:
            node_query_dict['aggs'] = children_queries
        if with_name:
            return {node.name: node_query_dict}
        return node_query_dict

    def __str__(self):
        self.show()
        return '<Aggregation>\n%s' % text(self._reader)


class ClientBoundQuery(Query):

    def __init__(self, client, index_name, mapping=None, from_=None, query=None, identifier=None):
        self.client = client
        self.index_name = index_name
        if client is not None:
            assert isinstance(client, Elasticsearch)
        self._query = query
        super(ClientBoundQuery, self).__init__(
            from_=from_,
            mapping=mapping,
            identifier=identifier
        )

    def _clone(self, identifier=None, with_tree=False, deep=False):
        return ClientBoundQuery(
            client=self.client,
            index_name=self.index_name,
            mapping=self.tree_mapping,
            identifier=identifier,
            query=self._query,
            from_=self if with_tree else None
        )

    def _execute(self, aggregation, index=None, query=None):
        body = {"aggs": aggregation, "size": 0}
        if query:
            body['query'] = query
        return self.client.search(index=index, body=body)

    def execute(self, index=None, **kwargs):
        body = {"size": 0}
        if query:
            body['query'] = query
        return self.client.search(index=index, body=body)
