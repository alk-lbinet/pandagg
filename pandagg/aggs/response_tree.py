#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pandagg.aggs import Nested
from pandagg.tree import Tree, Node
from pandagg.utils import TreeBasedObj, bool_if_required
from collections import OrderedDict, defaultdict


class PrettyNode:
    # class to display pretty nodes while working with trees
    def __init__(self, pretty):
        self.pretty = pretty


class ResponseNode(Node):

    REPR_SIZE = 60

    def __init__(self, aggregation_node, value, lvl, key=None, override_current_level=None, identifier=None):
        self.aggregation_node = aggregation_node
        self.value = value
        self.lvl = lvl
        # `override_current_level` is only used to create root node of response tree
        self.current_level = override_current_level or aggregation_node.agg_name
        self.current_key = key
        if self.current_key is not None:
            self.path = '%s_%s' % (self.current_level.replace('.', '_'), self.current_key)
        else:
            self.path = self.current_level.replace('.', '_')
        pretty = self._str_current_level(
            level=self.current_level,
            key=self.current_key,
            lvl=self.lvl, sep='=',
            value=self.extract_bucket_value()
        )
        super(ResponseNode, self).__init__(data=PrettyNode(pretty=pretty), identifier=identifier)

    @classmethod
    def _str_current_level(cls, level, key, lvl, sep=':', value=None):
        s = level
        if key is not None:
            s = '%s%s%s' % (s, sep, key)
        if value is not None:
            pad = max(cls.REPR_SIZE - 4 * lvl - len(s) - len(str(value)), 4)
            s = s + ' ' * pad + str(value)
        return s

    def extract_bucket_value(self, value_as_dict=False):
        attrs = self.aggregation_node.VALUE_ATTRS
        if value_as_dict:
            return {attr_: self.value.get(attr_) for attr_ in attrs}
        return self.value.get(attrs[0])

    def _bind(self, tree):
        return TreeBoundResponseNode(
            tree=tree,
            aggregation_node=self.aggregation_node,
            value=self.value,
            lvl=self.lvl,
            key=self.current_key,
            identifier=self.identifier
        )

    def __repr__(self):
        return u'<Bucket, identifier={identifier}>\n{pretty}'\
            .format(identifier=self.identifier, pretty=self.data.pretty).encode('utf-8')


class TreeBoundResponseNode(ResponseNode):

    def __init__(self, tree, aggregation_node, value, lvl, identifier, key=None):
        self._tree = tree
        super(TreeBoundResponseNode, self).__init__(
            aggregation_node=aggregation_node,
            value=value,
            lvl=lvl,
            key=key,
            identifier=identifier
        )

    def bucket_properties(self, end_level=None, depth=None):
        """Bucket properties (including parents) relative to this tree.
        TODO - optimize using rsearch
        """
        return self._tree.bucket_id_dict(self, end_level=end_level, depth=depth)

    def build_filter(self):
        """Build query filtering documents belonging to that bucket.
        """
        agg_tree = self._tree.agg_tree
        mapping_tree = agg_tree.tree_mapping

        aggs_keys = [
            (agg_tree[level], key) for
            level, key in self.bucket_properties().items()
        ]

        filters_per_nested_level = defaultdict(list)

        for level_agg, key in aggs_keys:
            level_agg_filter = level_agg.get_filter(key)
            # remove unnecessary match_all filters
            if level_agg_filter is not None and 'match_all' not in level_agg_filter:
                current_nested = agg_tree.applied_nested_path_at_node(level_agg.identifier)
                filters_per_nested_level[current_nested].append(level_agg_filter)

        # order nested by depth, deepest to highest
        # TODO - handle nested hierarchies (if there are multiple layers of nested, in different branches)
        ordered_nested = sorted(filters_per_nested_level.keys(), key=lambda x: mapping_tree.depth(x) if x else -1, reverse=True)

        current_conditions = []
        for nested in ordered_nested:
            level_condition = bool_if_required(filters_per_nested_level[nested])
            if nested:
                level_condition = {
                    'nested': {
                        'path': nested,
                        'query': level_condition
                    }
                }
            current_conditions.append(level_condition)
        return bool_if_required(current_conditions)


class ResponseTree(Tree):

    def __init__(self, agg_tree, identifier=None):
        super(ResponseTree, self).__init__(identifier=identifier)
        self.agg_tree = agg_tree

    def get_instance(self, identifier):
        return ResponseTree(agg_tree=self.agg_tree, identifier=identifier)

    def parse_aggregation(self, raw_response):
        # init tree with fist node called 'aggs'
        agg_node = self.agg_tree[self.agg_tree.root]
        response_node = ResponseNode(
            aggregation_node=agg_node,
            value=raw_response,
            override_current_level='aggs',
            lvl=0,
            identifier='crafted_root'
        )
        self.add_node(response_node)
        self._parse_node_with_children(agg_node, response_node)
        return self

    def _parse_node_with_children(self, agg_node, parent_node, lvl=1):
        agg_value = parent_node.value.get(agg_node.agg_name)
        if agg_value:
            # if no data is present, elasticsearch doesn't return any bucket, for instance for TermAggregations
            for key, value in agg_node.extract_buckets(agg_value):
                bucket = ResponseNode(aggregation_node=agg_node, key=key, value=value, lvl=lvl + 1)
                self.add_node(bucket, parent_node.identifier)
                for child in self.agg_tree.children(agg_node.agg_name):
                    self._parse_node_with_children(agg_node=child, parent_node=bucket, lvl=lvl + 1)

    def bucket_id_dict(self, bucket, properties=None, end_level=None, depth=None):
        if properties is None:
            properties = OrderedDict()
        properties[bucket.current_level] = bucket.current_key
        if depth is not None:
            depth -= 1
        parent = self.parent(bucket.identifier)
        if bucket.current_level == end_level or depth == 0 or parent is None or parent.identifier == 'crafted_root':
            return properties
        return self.bucket_id_dict(parent, properties, end_level, depth)

    def show(self, data_property='pretty', **kwargs):
        return super(ResponseTree, self).show(data_property=data_property)

    def __repr__(self):
        self.show()
        return (u'<{class_}>\n{tree}'.format(class_=self.__class__.__name__, tree=self._reader)).encode('utf-8')


class AggResponse(TreeBasedObj):

    _NODE_PATH_ATTR = 'path'

    def __call__(self, *args, **kwargs):
        initial_tree = self._tree if self._initial_tree is None else self._initial_tree
        root_bucket = self._tree[self._tree.root]
        return root_bucket._bind(initial_tree)
