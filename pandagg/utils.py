#!/usr/bin/env python
# -*- coding: utf-8 -*-


# adapted from https://github.com/elastic/elasticsearch-dsl-py/blob/master/elasticsearch_dsl/utils.py#L162
from six import add_metaclass


class DslMeta(type):
    """
    Base Metaclass for DslBase subclasses that builds a registry of all classes
    for given DslBase subclass (== all the query types for the Query subclass
    of DslBase).

    It then uses the information from that registry (as well as `name` and
    `deserializer` attributes from the base class) to construct any subclass based
    on it's name.
    """

    _types = {}

    def __init__(cls, name, bases, attrs):
        super(DslMeta, cls).__init__(name, bases, attrs)
        # skip for DSLMixin
        if not hasattr(cls, "_type_name") or cls._type_name is None:
            return

        if not hasattr(cls, "KEY") or cls.KEY is None:
            # abstract base class, register its shortcut
            cls._types[cls._type_name] = cls
            # and create a registry for subclasses
            if not hasattr(cls, "_classes"):
                cls._classes = {}
        elif cls.KEY not in cls._classes:
            # normal class, register it
            cls._classes[cls.KEY] = cls


@add_metaclass(DslMeta)
class DSLMixin(object):
    """Base class for all DSL objects - queries, filters, aggregations etc. Wraps
    a dictionary representing the object's json."""

    @classmethod
    def _get_dsl_class(cls, name):
        try:
            return cls._classes[name]
        except KeyError:
            raise NotImplementedError(
                "DSL class `{}` does not exist in {}.".format(name, cls._type_name)
            )

    @staticmethod
    def _get_dsl_type(name):
        try:
            return DslMeta._types[name]
        except KeyError:
            raise ValueError("DSL type %s does not exist." % name)


def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    return obj


def equal_queries(d1, d2):
    """Compares if two queries are equivalent (do not consider nested list orders)."""
    return ordered(d1) == ordered(d2)


def equal_search(s1, s2):
    if not isinstance(s1, dict) or not isinstance(s2, dict):
        raise ValueError("not a search")
    s1 = s1.copy()
    s2 = s2.copy()
    # sort order matters
    if not s1.pop("sort", None) == s2.pop("sort", None):
        return False
    return equal_queries(s1, s2)
