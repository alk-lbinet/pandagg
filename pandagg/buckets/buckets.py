#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from treelib import Node
from pandagg.utils import PrettyNode


class Bucket(Node):

    REPR_SIZE = 60

    def __init__(self, depth, value, key=None, aggregation_node=None):
        self.aggregation_node = aggregation_node
        self.value = value
        self.level = aggregation_node.agg_name if aggregation_node is not None else 'root'
        self.depth = depth
        self.key = key
        if self.key is not None:
            self.path = '%s_%s' % (self.level.replace('.', '_'), self.key)
        else:
            self.path = self.level.replace('.', '_')
        pretty = self._str_current_level(
            level=self.level,
            key=self.key,
            depth=self.depth, sep='=',
            value=self.value
        )
        super(Bucket, self).__init__(data=PrettyNode(pretty=pretty))

    @classmethod
    def _str_current_level(cls, level, key, depth, sep=':', value=None):
        s = level
        if key is not None:
            s = '%s%s%s' % (s, sep, key)
        if value is not None:
            pad = max(cls.REPR_SIZE - 4 * depth - len(s) - len(str(value)), 4)
            s = s + ' ' * pad + str(value)
        return s

    def __str__(self):
        return u'<Bucket, identifier={identifier}>\n{pretty}' \
            .format(identifier=self.identifier, pretty=self.data.pretty)