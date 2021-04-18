#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from builtins import str as text
from six import text_type

import json

from future.utils import python_2_unicode_compatible

from pandagg.tree._tree import Tree
from pandagg.tree.mapping import _mapping

from pandagg.node.aggs.abstract import BucketAggNode, AggClause, Root, A
from pandagg.node.aggs.bucket import Nested, ReverseNested
from pandagg.node.aggs.pipeline import BucketSelector, BucketSort


@python_2_unicode_compatible
class Aggs(Tree):
    """
    Combination of aggregation clauses. This class provides handful methods to build an aggregation (see
    :func:`~pandagg.tree.aggs.Aggs.aggs` and :func:`~pandagg.tree.aggs.Aggs.groupby`), and is used as well
    to parse aggregations response in easy to manipulate formats.

    Mapping declaration is optional, but doing so validates aggregation validity and automatically handles missing
    nested clauses.

    Accept following syntaxes:

    from a dict:
    >>> Aggs({"per_user": {"terms": {"field": "user"}}})

    from an other Aggs instance:
    >>> Aggs(Aggs({"per_user": {"terms": {"field": "user"}}}))

    dict with AggClause instances as values:
    >>> from pandagg.aggs import Terms, Avg
    >>> Aggs({'per_user': Terms(field='user')})

    :param mapping: ``dict`` or ``pandagg.tree.mapping.Mapping`` Mapping of requested indice(s). If provided, will
    check aggregations validity.
    :param nested_autocorrect: ``bool`` In case of missing nested clauses in aggregation, if True, automatically
    add missing nested clauses, else raise error. Ignored if mapping is not provided.
    :param _groupby_ptr: ``str`` identifier of aggregation clause used as grouping element (used by `clone` method).
    """

    node_class = AggClause

    def __init__(
        self, aggs=None, mapping=None, nested_autocorrect=None, _groupby_ptr=None
    ):
        self.mapping = _mapping(mapping)
        self.nested_autocorrect = nested_autocorrect
        super(Aggs, self).__init__()

        # the root node of an aggregation is just the initial empty dict
        root_node = Root()
        self.insert_node(root_node)
        # identifier of clause used for groupby
        self._groupby_ptr = self.root if _groupby_ptr is None else _groupby_ptr

        if aggs is not None:
            self._insert_aggs(aggs, at_root=True)

    def __nonzero__(self):
        return bool(self.to_dict())

    __bool__ = __nonzero__

    def _insert_agg(
        self, name, node, insert_below_id=None, at_root=None, groupby_id=False
    ):
        """
        Using flat declaration:
        >>> Aggs().agg("per_user", "terms", field="user")
        >>> Aggs().agg("per_user", {"terms": {"field": "user"}})

        Using DSL class:
        >>> from pandagg.aggs import Terms
        >>> Aggs().agg("per_user", Terms(field='user'))

        Agg node insertion, accepts following syntax:
        - name="per_user", type_or_agg="terms", field="user"
        - name="per_user", type_or_agg=Terms(field='user')
        - name="per_user", type_or_agg={"terms": {"field": "user"}}

        insert children aggs as well:
        - name="per_user", type_or_agg="terms", field="user", aggs={"avg_spent_time": {"avg": {"field": "spent_time"}}}
        - name="per_user", type_or_agg=Terms(field='user', aggs={"avg_spent_time": Avg(field="spent_time")})
        - name="per_user", type_or_agg={"field": "user", aggs: {"avg_spent_time": {"avg": {"field": "spent_time"}}}}
        """
        if insert_below_id and at_root:
            raise ValueError('Must define at most one of "insert_below" or "at_root".')
        if at_root:
            insert_below_id = self.root
        # based on last groupby pointer
        if insert_below_id is None:
            insert_below_id = self._groupby_ptr

        if not isinstance(name, text_type):
            raise ValueError('Agg "name" must be a str.')

        _children_aggs = node._children or {}

        if groupby_id:
            if _children_aggs:
                raise ValueError("Cannot group by multiple aggs at once.")
            subs = [
                self.drop_subtree(cid) for cid in self.children_ids(insert_below_id)
            ]
            self.insert(node, key=name, parent_id=insert_below_id)
            for sub_key, sub_tree in subs:
                self.insert(sub_tree, key=sub_key, parent_id=node.identifier)
            # moving pointer when using groupby
            self._groupby_ptr = node.identifier
            return

        # in aggs mode, do not move pointer
        self.insert_node(node=node, key=name, parent_id=insert_below_id)
        for child_name, child in _children_aggs.items():
            child_node = A(child_name, child)
            self._insert_agg(
                name=child_name, node=child_node, insert_below_id=node.identifier
            )

    def _clone_init(self, deep=False):
        return Aggs(
            mapping=self.mapping.clone(deep=deep) if self.mapping is not None else None,
            nested_autocorrect=self.nested_autocorrect,
            _groupby_ptr=self._groupby_ptr,
        )

    def _is_eligible_grouping_node(self, nid):
        """
        Return whether node can be used as grouping node.
        """
        _, node = self.get(nid)
        if not isinstance(node, BucketAggNode):
            return False
        # special aggregations not returning anything
        if isinstance(node, (BucketSelector, BucketSort)):
            return False
        return True

    @property
    def _deepest_linear_bucket_agg(self):
        """
        Return deepest bucket aggregation node identifier (pandagg.nodes.abstract.BucketAggNode) of that aggregation
        that neither has siblings, nor has an ancestor with siblings.
        """
        if len(self._nodes_map) <= 1:
            return self.root
        last_bucket_agg_id = self.root
        children = [
            c
            for k, c in self.children(last_bucket_agg_id)
            if self._is_eligible_grouping_node(c.identifier)
        ]
        while len(children) == 1:
            last_agg_node = children[0]
            if not self._is_eligible_grouping_node(last_agg_node.identifier):
                break
            last_bucket_agg_id = last_agg_node.identifier
            children = [
                c
                for k, c in self.children(last_bucket_agg_id)
                if self._is_eligible_grouping_node(c.identifier)
            ]
        return last_bucket_agg_id

    def grouped_by(self, agg_name=None, deepest=False):
        """
        Define which aggregation will be used as grouping pointer.

        Either provide an aggregation name, either specify 'deepest=True' to consider deepest linear eligible
        aggregation node as pointer.
        """
        if agg_name and deepest:
            raise ValueError('Should provide only one of "agg_name" or "deepest".')
        new_agg = self.clone()
        if agg_name:
            nid = new_agg.id_from_key(agg_name)
            if not new_agg._is_eligible_grouping_node(nid):
                raise ValueError("Cannot group by <%s> aggregation" % agg_name)
            new_agg._groupby_ptr = nid
            return new_agg
        if deepest:
            new_agg._groupby_ptr = new_agg._deepest_linear_bucket_agg
            return new_agg
        # no argument was provided, reset pointer to root
        new_agg._groupby_ptr = new_agg.root
        return new_agg

    def groupby(self, name, type_or_agg=None, insert_below=None, at_root=None, **body):
        """
        Arrange passed aggregations in vertical/nested manner, above or below another agg clause.

        Given the initial aggregation::

            A──> B
            └──> C

        If `insert_below` = 'A'::

            A──> new──> B
                  └──> C

        >>> Aggs()\
        >>> .groupby('per_user_id', 'terms', field='user_id')
        {"per_user_id":{"terms":{"field":"user_id"}}}

        >>> Aggs()\
        >>> .groupby('per_user_id', {'terms': {"field": "user_id"}})
        {"per_user_id":{"terms":{"field":"user_id"}}}

        >>> from pandagg.aggs import Terms
        >>> Aggs()\
        >>> .groupby('per_user_id', Terms(field="user_id"))
        {"per_user_id":{"terms":{"field":"user_id"}}}

        :rtype: pandagg.aggs.Aggs
        """
        new_agg = self.clone()
        insert_below_id = (
            None if insert_below is None else new_agg.id_from_key(insert_below)
        )
        node = A(name, type_or_agg, **body)
        new_agg._insert_agg(
            name=name,
            node=node,
            insert_below_id=insert_below_id,
            at_root=at_root,
            groupby_id=True,
        )
        return new_agg

    def aggs(self, aggs, insert_below=None, at_root=False):
        """
        Insert provided aggs in copy of initial Aggs.

        Accept following syntaxes for provided aggs:

        python dict format:
        >>> Aggs().aggs({'some_agg': {'terms': {'field': 'some_field'}}, 'other_agg': {'avg': {'field': 'age'}}})

        Aggs instance:
        >>> Aggs().aggs(Aggs({'some_agg': {'terms': {'field': 'some_field'}}, 'other_agg': {'avg': {'field': 'age'}}}))

        dict with Agg clauses values:
        >>> from pandagg.aggs import Terms, Avg
        >>> Aggs().aggs({'some_agg': Terms(field='some_field'), 'other_agg': Avg(field='age')})

        :param aggs: aggregations to insert into existing aggregation
        :param insert_below: name of aggregation below which provided aggs should be inserted
        :param at_root: if True, aggregation is inserted at root
        :return: copy of initial Aggs with provided aggs inserted
        """
        new_agg = self.clone(with_nodes=True)
        if insert_below is not None:
            insert_below = new_agg.id_from_key(insert_below)
        new_agg._insert_aggs(aggs=aggs, insert_below_id=insert_below, at_root=at_root)
        return new_agg

    def _insert_aggs(self, aggs, insert_below_id=None, at_root=False):
        """Insert aggs clauses in current Aggs (mutate current instance)"""
        if at_root:
            insert_below_id = self.root
        elif not insert_below_id:
            # parent based on last groupby pointer
            insert_below_id = self._groupby_ptr

        if aggs is None:
            return
        if isinstance(aggs, Aggs):
            self.merge(aggs, nid=insert_below_id)
            self._groupby_ptr = self.root
            return
        if isinstance(aggs, dict):
            for agg_name, agg_body in aggs.items():
                node = A(agg_name, agg_body)
                self._insert_agg(
                    name=agg_name, node=node, insert_below_id=insert_below_id
                )
            return
        raise TypeError("Unsupported aggs type %s for Aggs" % type(aggs))

    def agg(self, name, type_or_agg=None, insert_below=None, at_root=False, **body):
        """
        Insert provided agg clause in copy of initial Aggs.

        Accept following syntaxes for type_or_agg argument:

        string, with body provided in kwargs
        >>> Aggs().agg(name='some_agg', type_or_agg='terms', field='some_field')

        python dict format:
        >>> Aggs().agg(name='some_agg', type_or_agg={'terms': {'field': 'some_field'})

        AggClause instance:
        >>> from pandagg.aggs import Terms
        >>> Aggs().agg(name='some_agg', type_or_agg=Terms(field='some_field'))

        :param name: inserted agg clause name
        :param type_or_agg: either agg type (str), or agg clause of dict format, or AggClause instance
        :param insert_below: name of aggregation below which provided aggs should be inserted
        :param at_root: if True, aggregation is inserted at root
        :param body: aggregation clause body when providing string type_of_agg (remaining kwargs)
        :return: copy of initial Aggs with provided agg inserted
        """
        new_agg = self.clone(with_nodes=True)
        if insert_below is not None:
            insert_below = new_agg.id_from_key(insert_below)
        node = A(name, type_or_agg, **body)
        new_agg._insert_agg(
            name=name, node=node, insert_below_id=insert_below, at_root=at_root
        )
        return new_agg

    def to_dict(self, from_=None, depth=None):
        if self.root is None:
            return None
        from_ = self.root if from_ is None else from_
        _, node = self.get(from_)
        children_queries = {}
        if depth is None or depth > 0:
            if depth is not None:
                depth -= 1
            for child_name, child_node in self.children(node.identifier):
                children_queries[child_name] = self.to_dict(
                    from_=child_node.identifier, depth=depth
                )
        if node.identifier == self.root:
            return children_queries
        node_query_dict = node.to_dict()
        if children_queries:
            node_query_dict["aggs"] = children_queries
        return node_query_dict

    def applied_nested_path_at_node(self, nid):
        # from current node to root
        for id_ in self.ancestors_ids(nid, include_current=True):
            _, node = self.get(id_)
            if isinstance(node, (Nested, ReverseNested)):
                return node.path
        return None

    def _insert_node_below(self, node, parent_id, key, by_path):
        """
        If mapping is provided, nested aggregations are automatically applied.
        """
        # if aggregation node is explicitely nested or reverse nested aggregation, do not override, but validate
        if (
            isinstance(node, Nested)
            or isinstance(node, ReverseNested)
            or not self.mapping
            or not hasattr(node, "field")
            or self.root is None
        ):
            return super(Aggs, self)._insert_node_below(node, parent_id, key, by_path)

        self.mapping.validate_agg_node(node)

        # from deepest to highest
        required_nested_level = self.mapping.nested_at_field(node.field)

        current_nested_level = self.applied_nested_path_at_node(parent_id)
        if current_nested_level == required_nested_level:
            return super(Aggs, self)._insert_node_below(node, parent_id, key, by_path)
        if not self.nested_autocorrect:
            raise ValueError(
                "Invalid %s agg on %s field. Invalid nested: expected %s, current %s."
                % (node.KEY, node.field, required_nested_level, current_nested_level)
            )
        if current_nested_level and (
            required_nested_level or "" in current_nested_level
        ):
            # requires reverse-nested
            # check if already exists in direct children, else create it
            child_reverse_nested = next(
                (
                    n
                    for k, n in self.children(parent_id)
                    if isinstance(n, ReverseNested) and n.path == required_nested_level
                ),
                None,
            )
            if child_reverse_nested:
                return super(Aggs, self)._insert_node_below(
                    node, child_reverse_nested.identifier, key, by_path
                )
            else:
                rv_node = ReverseNested()
                super(Aggs, self).insert_node(
                    rv_node,
                    parent_id=parent_id,
                    key="reverse_nested_below_%s" % self.get_key(parent_id),
                )
                return super(Aggs, self)._insert_node_below(
                    node, rv_node.identifier, key, by_path
                )

        # requires nested - apply all required nested fields
        for nested_lvl in reversed(self.mapping.list_nesteds_at_field(node.field)):
            if current_nested_level != nested_lvl:
                # check if already exists in direct children, else create it
                child_nested = next(
                    (
                        n
                        for k, n in (
                            self.children(parent_id) if parent_id is not None else []
                        )
                        if isinstance(n, Nested) and n.path == nested_lvl
                    ),
                    None,
                )
                if child_nested:
                    parent_id = child_nested.identifier
                    continue
                nested_node_name = (
                    "nested_below_root"
                    if parent_id is None
                    else "nested_below_%s" % self.get_key(parent_id)
                )
                nested_node = Nested(path=nested_lvl)
                super(Aggs, self)._insert_node_below(
                    nested_node, parent_id, nested_node_name, by_path
                )
                parent_id = nested_node.identifier
        super(Aggs, self)._insert_node_below(node, parent_id, key, by_path)

    def apply_reverse_nested(self, nid=None):
        for k, leaf in self.leaves(nid):
            if isinstance(leaf, BucketAggNode) and self.applied_nested_path_at_node(
                leaf.identifier
            ):
                self.add_node(
                    ReverseNested(),
                    insert_below=leaf.identifier,
                    key="reverse_nested_%s" % leaf.identifier,
                )

    def __str__(self):
        return json.dumps(self.to_dict(), indent=2)

    def show(self, *args, line_max_length=80, **kwargs):
        root_children = self.children(self.root)
        if len(root_children) == 0:
            return "<Aggregations> empty"
        if len(root_children) == 1:
            child_id = root_children[0][1].identifier
            return "<Aggregations>\n%s" % text(
                super(Tree, self).show(
                    child_id, *args, line_max_length=line_max_length, **kwargs
                )
            )

        return "<Aggregations>\n%s" % text(
            super(Tree, self).show(*args, line_max_length=line_max_length, **kwargs)
        )
