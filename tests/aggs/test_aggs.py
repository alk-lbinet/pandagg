#!/usr/bin/env python
# -*- coding: utf-8 -*-

# =============================================================================
#                                   IMPORTS
# =============================================================================

from unittest import TestCase

from treelib.exceptions import MultipleRootError
from pandagg.aggs import Agg
from pandagg.exceptions import AbsentMappingFieldError, InvalidOperationMappingFieldError
from pandagg.mapping import MappingTree, Mapping
from pandagg.nodes import Avg, Max, Min, DateHistogram, Terms, Filter

from tests.mapping.mapping_example import MAPPING_NAME, MAPPING_DETAIL


EXPECTED_DICT_AGG = {
    "week": {
        "date_histogram": {
            "field": "date",
            "format": "yyyy-MM-dd",
            "interval": "1w"
        },
        "aggs": {
            "nested_below_week": {
                "nested": {
                    "path": "local_metrics"
                },
                "aggs": {
                    "local_metrics.field_class.name": {
                        "terms": {
                            "field": "local_metrics.field_class.name",
                            "size": 10
                        },
                        "aggs": {
                            "avg_f1_score": {
                                "avg": {
                                    "field": "local_metrics.performance.test.f1_score"
                                }
                            },
                            "max_f1_score": {
                                "max": {
                                    "field": "local_metrics.performance.test.f1_score"
                                }
                            },
                            "min_f1_score": {
                                "min": {
                                    "field": "local_metrics.performance.test.f1_score"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

expected_repr = u"""<Aggregation>
week
└── nested_below_week
    └── local_metrics.field_class.name
        ├── avg_f1_score
        ├── max_f1_score
        └── min_f1_score
"""


class AggTestCase(TestCase):

    def test_add_node_with_mapping(self):
        with_mapping = Agg(mapping={MAPPING_NAME: MAPPING_DETAIL})
        self.assertEqual(len(with_mapping.nodes.keys()), 0)

        # add regular node
        with_mapping.add_node(Terms('workflow', field='workflow'))
        self.assertEqual(len(with_mapping.nodes.keys()), 1)

        # try to add second root fill fail
        with self.assertRaises(MultipleRootError):
            with_mapping.add_node(Terms('classification_type', field='classification_type'))

        # try to add field aggregation on non-existing field will fail
        with self.assertRaises(AbsentMappingFieldError):
            with_mapping.add_node(
                node=Terms('imaginary_agg', field='imaginary_field'),
                pid='workflow'
            )
        self.assertEqual(len(with_mapping.nodes.keys()), 1)

        # try to add aggregation on a non-compatible field will fail
        with self.assertRaises(InvalidOperationMappingFieldError):
            with_mapping.add_node(
                node=Avg('average_of_string', field='classification_type'),
                pid='workflow'
            )
        self.assertEqual(len(with_mapping.nodes.keys()), 1)

        # add field aggregation on field passing through nested will automatically add nested
        with_mapping.add_node(
            node=Avg('local_f1_score', field='local_metrics.performance.test.f1_score'),
            pid='workflow'
        )
        self.assertEqual(len(with_mapping.nodes.keys()), 3)
        self.assertEqual(
            with_mapping.__repr__().decode('utf-8'),
            u"""<Aggregation>
workflow
└── nested_below_workflow
    └── local_f1_score
"""
        )
        self.assertIn('nested_below_workflow', with_mapping)
        nested_node = with_mapping['nested_below_workflow']
        self.assertEqual(nested_node.AGG_TYPE, 'nested')
        self.assertEqual(nested_node.path, 'local_metrics')

        # add other agg requiring nested will reuse nested agg as parent
        with_mapping.add_node(
            node=Avg('local_precision', field='local_metrics.performance.test.precision'),
            pid='workflow'
        )
        self.assertEqual(
            with_mapping.__repr__().decode('utf-8'),
            u"""<Aggregation>
workflow
└── nested_below_workflow
    ├── local_f1_score
    └── local_precision
"""
        )
        self.assertEqual(len(with_mapping.nodes.keys()), 4)

        # add under a nested parent a field aggregation that requires to be located under root will automatically
        # add reverse-nested
        with_mapping.add_node(
            node=Terms('language_terms', field='language'),
            pid='nested_below_workflow'
        )
        self.assertEqual(len(with_mapping.nodes.keys()), 6)
        self.assertEqual(
            with_mapping.__repr__().decode('utf-8'),
            u"""<Aggregation>
workflow
└── nested_below_workflow
    ├── local_f1_score
    ├── local_precision
    └── reverse_nested_below_nested_below_workflow
        └── language_terms
"""
        )

    def test_add_node_without_mapping(self):
        without_mapping = Agg()
        self.assertEqual(len(without_mapping.nodes.keys()), 0)

        # add regular node
        without_mapping.add_node(Terms('workflow_not_existing', field='field_not_existing'))
        self.assertEqual(len(without_mapping.nodes.keys()), 1)

    # TODO - finish these tests
    def test_paste_tree_with_mapping(self):
        # with explicit nested
        initial_agg_1 = Agg(
            mapping={MAPPING_NAME: MAPPING_DETAIL},
            from_={
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w"
                    }
                }
            }
        )
        self.assertEqual(initial_agg_1.nodes.keys(), ['week'])
        pasted_agg_1 = Agg(
            from_={
                "nested_below_week": {
                    "nested": {
                        "path": "local_metrics"
                    },
                    "aggs": {
                        "local_metrics.field_class.name": {
                            "terms": {
                                "field": "local_metrics.field_class.name",
                                "size": 10
                            }
                        }
                    }
                }
            }
        )
        self.assertEqual(set(pasted_agg_1.nodes.keys()), {'nested_below_week', 'local_metrics.field_class.name'})

        initial_agg_1.paste('week', pasted_agg_1)
        self.assertEqual(set(initial_agg_1.nodes.keys()), {'week', 'nested_below_week', 'local_metrics.field_class.name'})
        self.assertEqual(
            initial_agg_1.__repr__().decode("utf-8"),
            u"""<Aggregation>
week
└── nested_below_week
    └── local_metrics.field_class.name
"""
        )

        # without explicit nested
        initial_agg_2 = Agg(
            mapping={MAPPING_NAME: MAPPING_DETAIL},
            from_={
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w"
                    }
                }
            }
        )
        self.assertEqual(initial_agg_2.nodes.keys(), ['week'])
        pasted_agg_2 = Agg(
            from_={
                "local_metrics.field_class.name": {
                    "terms": {
                        "field": "local_metrics.field_class.name",
                        "size": 10
                    }
                }
            }
        )
        self.assertEqual(pasted_agg_2.nodes.keys(), ['local_metrics.field_class.name'])

        initial_agg_2.paste("week", pasted_agg_2)
        self.assertEqual(set(initial_agg_2.nodes.keys()), {'week', 'nested_below_week', 'local_metrics.field_class.name'})
        self.assertEqual(
            initial_agg_2.__repr__().decode("utf-8"),
            u"""<Aggregation>
week
└── nested_below_week
    └── local_metrics.field_class.name
"""
        )

    def test_paste_tree_without_mapping(self):
        # with explicit nested
        initial_agg_1 = Agg(
            mapping=None,
            from_={
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w"
                    }
                }
            }
        )
        self.assertEqual(initial_agg_1.nodes.keys(), ['week'])

        pasted_agg_1 = Agg(
            from_={
                "nested_below_week": {
                    "nested": {
                        "path": "local_metrics"
                    },
                    "aggs": {
                        "local_metrics.field_class.name": {
                            "terms": {
                                "field": "local_metrics.field_class.name",
                                "size": 10
                            }
                        }
                    }
                }
            }
        )
        self.assertEqual(set(pasted_agg_1.nodes.keys()), {'nested_below_week', "local_metrics.field_class.name"})

        initial_agg_1.paste('week', pasted_agg_1)
        self.assertEqual(set(initial_agg_1.nodes.keys()), {'week', 'nested_below_week', "local_metrics.field_class.name"})
        self.assertEqual(
            initial_agg_1.__repr__().decode("utf-8"),
            u"""<Aggregation>
week
└── nested_below_week
    └── local_metrics.field_class.name
"""
        )

        # without explicit nested (will NOT add nested)
        initial_agg_2 = Agg(
            mapping=None,
            from_={
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w"
                    }
                }
            }
        )
        self.assertEqual(initial_agg_2.nodes.keys(), ["week"])

        pasted_agg_2 = Agg(
            from_={
                "local_metrics.field_class.name": {
                    "terms": {
                        "field": "local_metrics.field_class.name",
                        "size": 10
                    }
                }
            }
        )
        self.assertEqual(pasted_agg_2.nodes.keys(), ["local_metrics.field_class.name"])

        initial_agg_2.paste("week", pasted_agg_2)
        self.assertEqual(set(initial_agg_2.nodes.keys()), {"week", "local_metrics.field_class.name"})
        self.assertEqual(
            initial_agg_2.__repr__().decode("utf-8"),
            u"""<Aggregation>
week
└── local_metrics.field_class.name
"""
        )

    def test_validate(self):
        pass

    def test_interpret_agg_string(self):
        empty_agg = Agg()
        empty_agg._interpret_agg(insert_below=None, element='some_field')
        self.assertEqual(
            empty_agg.query_dict(),
            {'some_field': {'terms': {'field': 'some_field', 'size': 20}}}
        )

        # with default size
        empty_agg = Agg()
        empty_agg._interpret_agg(insert_below=None, element='some_field', default_size=10)
        self.assertEqual(
            empty_agg.query_dict(),
            {'some_field': {'terms': {'field': 'some_field', 'size': 10}}}
        )

        # with parent
        agg = Agg(from_={'root_agg_name': {'terms': {'field': 'some_field', 'size': 5}}})
        agg._interpret_agg(insert_below='root_agg_name', element='child_field')
        self.assertEqual(
            agg.query_dict(),
            {
                "root_agg_name": {
                    "aggs": {
                        "child_field": {
                            "terms": {
                                "field": "child_field",
                                "size": 20
                            }
                        }
                    },
                    "terms": {
                        "field": "some_field",
                        "size": 5
                    }
                }
            }
        )

        # with required nested
        agg = Agg(
            from_={'term_workflow': {'terms': {'field': 'workflow', 'size': 5}}},
            mapping={MAPPING_NAME: MAPPING_DETAIL}
        )
        agg._interpret_agg(insert_below='term_workflow', element='local_metrics.field_class.name')
        self.assertEqual(
            agg.query_dict(),
            {
                "term_workflow": {
                    "aggs": {
                        "nested_below_term_workflow": {
                            "aggs": {
                                "local_metrics.field_class.name": {
                                    "terms": {
                                        "field": "local_metrics.field_class.name",
                                        "size": 20
                                    }
                                }
                            },
                            "nested": {
                                "path": "local_metrics"
                            }
                        }
                    },
                    "terms": {
                        "field": "workflow",
                        "size": 5
                    }
                }
            }
        )

        # TODO - check reverse nested implications
        # with required reverse-nested
        # (reusing nested example)
        # agg._interpret_agg(insert_below='local_metrics.field_class.name', element=['language'])

    def test_interpret_node(self):
        empty_agg = Agg()
        node = Terms(
            agg_name='some_name',
            field='some_field',
            size=10
        )
        empty_agg._interpret_agg(insert_below=None, element=node)
        self.assertEqual(
            empty_agg.query_dict(),
            {
                "some_name": {
                    "terms": {
                        "field": "some_field",
                        "size": 10
                    }
                }
            }
        )
        # with parent with required nested
        agg = Agg(
            from_={'term_workflow': {'terms': {'field': 'workflow', 'size': 5}}},
            mapping={MAPPING_NAME: MAPPING_DETAIL}
        )
        node = Avg(
            agg_name='min_local_f1',
            field='local_metrics.performance.test.f1_score'
        )
        agg._interpret_agg(insert_below='term_workflow', element=node)
        self.assertEqual(
            agg.query_dict(),
            {
                "term_workflow": {
                    "aggs": {
                        "nested_below_term_workflow": {
                            "aggs": {
                                "min_local_f1": {
                                    "avg": {
                                        "field": "local_metrics.performance.test.f1_score"
                                    }
                                }
                            },
                            "nested": {
                                "path": "local_metrics"
                            }
                        }
                    },
                    "terms": {
                        "field": "workflow",
                        "size": 5
                    }
                }
            }
        )

    def test_query_dict(self):
        # empty
        self.assertEqual(Agg().query_dict(), {})

        # single node
        agg = Agg()
        node = Terms(
            agg_name='root_agg',
            field='some_field',
            size=10
        )
        agg.add_node(node)
        self.assertEqual(
            agg.query_dict(),
            {
                "root_agg": {
                    "terms": {
                        "field": "some_field",
                        "size": 10
                    }
                }
            }
        )

        # hierarchy
        agg.add_node(
            Terms(
                agg_name='other_name',
                field='other_field',
                size=30
            ),
            'root_agg'
        )
        agg.add_node(
            Avg(
                agg_name='avg_some_other_field',
                field='some_other_field'
            ),
            'root_agg'
        )
        self.assertEqual(
            agg.__repr__().decode('utf-8'),
            u"""<Aggregation>
root_agg
├── avg_some_other_field
└── other_name
"""
        )
        self.assertEqual(
            agg.query_dict(),
            {
                "root_agg": {
                    "aggs": {
                        "avg_some_other_field": {
                            "avg": {
                                "field": "some_other_field"
                            }
                        },
                        "other_name": {
                            "terms": {
                                "field": "other_field",
                                "size": 30
                            }
                        }
                    },
                    "terms": {
                        "field": "some_field",
                        "size": 10
                    }
                }
            }
        )

    def test_parse_group_by(self):
        pass

    def test_normalize_buckets(self):
        pass

    def test_parse_as_dict(self):
        pass

    def test_parse_as_dataframe(self):
        pass

    def test_agg_method(self):
        pass

    def test_groupby_method(self):
        pass

    def test_mapping_from_init(self):
        agg_from_dict_mapping = Agg(mapping={MAPPING_NAME: MAPPING_DETAIL})
        agg_from_tree_mapping = Agg(mapping=MappingTree(mapping_name=MAPPING_NAME, mapping_detail=MAPPING_DETAIL))
        agg_from_obj_mapping = Agg(mapping=Mapping(tree=MappingTree(mapping_name=MAPPING_NAME, mapping_detail=MAPPING_DETAIL)))
        self.assertEqual(
            agg_from_dict_mapping.tree_mapping.to_dict(),
            agg_from_tree_mapping.tree_mapping.to_dict()
        )
        self.assertEqual(
            agg_from_dict_mapping.tree_mapping.to_dict(),
            agg_from_obj_mapping.tree_mapping.to_dict()
        )
        self.assertIsInstance(agg_from_dict_mapping, Agg)
        self.assertIsInstance(agg_from_tree_mapping, Agg)
        self.assertIsInstance(agg_from_obj_mapping, Agg)

    def test_set_mapping(self):
        agg_from_dict_mapping = Agg() \
            .set_mapping(mapping={MAPPING_NAME: MAPPING_DETAIL})
        agg_from_tree_mapping = Agg() \
            .set_mapping(mapping=MappingTree(mapping_name=MAPPING_NAME, mapping_detail=MAPPING_DETAIL))
        agg_from_obj_mapping = Agg() \
            .set_mapping(mapping=Mapping(tree=MappingTree(mapping_name=MAPPING_NAME, mapping_detail=MAPPING_DETAIL)))
        self.assertEqual(
            agg_from_dict_mapping.tree_mapping.to_dict(),
            agg_from_tree_mapping.tree_mapping.to_dict()
        )
        self.assertEqual(
            agg_from_dict_mapping.tree_mapping.to_dict(),
            agg_from_obj_mapping.tree_mapping.to_dict()
        )
        # set mapping returns self
        self.assertIsInstance(agg_from_dict_mapping, Agg)
        self.assertIsInstance(agg_from_tree_mapping, Agg)
        self.assertIsInstance(agg_from_obj_mapping, Agg)

    def test_init_from_dict(self):
        agg = Agg(from_=EXPECTED_DICT_AGG, mapping={MAPPING_NAME: MAPPING_DETAIL})
        self.assertEqual(agg.query_dict(), EXPECTED_DICT_AGG)
        self.assertEqual(agg.__repr__().decode('utf-8'), expected_repr)

    def test_init_from_node_hierarchy(self):
        node_hierarchy = DateHistogram(
            agg_name='week',
            field='date',
            interval='1w',
            aggs=[
                Terms(
                    agg_name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                    aggs=[
                        Min(agg_name='min_f1_score', field='local_metrics.performance.test.f1_score'),
                        Max(agg_name='max_f1_score', field='local_metrics.performance.test.f1_score'),
                        Avg(agg_name='avg_f1_score', field='local_metrics.performance.test.f1_score')
                    ]
                )
            ]
        )
        agg = Agg(from_=node_hierarchy, mapping={MAPPING_NAME: MAPPING_DETAIL})
        self.assertEqual(agg.query_dict(), EXPECTED_DICT_AGG)
        self.assertEqual(agg.__repr__().decode('utf-8'), expected_repr)

    def test_groupby_and_agg(self):
        week = DateHistogram(agg_name='week', field='date', interval='1w')

        # default size defines size of terms aggregations, (impacts "local_metrics.field_class.name" terms agg)
        agg = Agg(mapping={MAPPING_NAME: MAPPING_DETAIL}) \
            .groupby([week, "local_metrics.field_class.name"], default_size=10) \
            .agg([
                Min(agg_name='min_f1_score', field='local_metrics.performance.test.f1_score'),
                Max(agg_name='max_f1_score', field='local_metrics.performance.test.f1_score'),
                Avg(agg_name='avg_f1_score', field='local_metrics.performance.test.f1_score')
            ])
        self.assertEqual(agg.query_dict(), EXPECTED_DICT_AGG)
        self.assertEqual(agg.__repr__().decode('utf-8'), expected_repr)

    def test_applied_nested_path_at_node(self):
        """ Check that correct nested path is detected at node levels:
        week
        └── nested_below_week
            └── local_metrics.field_class.name
                ├── avg_f1_score
                ├── max_f1_score
                └── min_f1_score
        """
        agg = Agg(from_=EXPECTED_DICT_AGG, mapping={MAPPING_NAME: MAPPING_DETAIL})

        self.assertEqual(agg.applied_nested_path_at_node('week'), None)
        for nid in ('nested_below_week', 'local_metrics.field_class.name', 'max_f1_score',
                    'max_f1_score', 'min_f1_score'):
            self.assertEqual(agg.applied_nested_path_at_node(nid), 'local_metrics')

    def test_deepest_linear_agg(self):
        # deepest_linear_bucket_agg
        """
        week
        └── nested_below_week
            └── local_metrics.field_class.name   <----- HERE because then metric aggregation
                └── avg_f1_score
        """
        node_hierarchy = DateHistogram(
            agg_name='week',
            field='date',
            interval='1w',
            aggs=[
                Terms(
                    agg_name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                    aggs=[
                        Min(
                            agg_name='min_f1_score',
                            field='local_metrics.performance.test.f1_score'
                        )
                    ]
                )
            ]
        )
        agg = Agg(from_=node_hierarchy, mapping={MAPPING_NAME: MAPPING_DETAIL})
        self.assertEqual(agg.deepest_linear_bucket_agg, 'local_metrics.field_class.name')

        # week is last bucket linear bucket
        node_hierarchy_2 = DateHistogram(
            agg_name='week',
            field='date',
            interval='1w',
            aggs=[
                Terms(
                    agg_name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10
                ),
                Filter(
                    agg_name="f1_score_above_threshold",
                    filter_={
                        "range": {
                            "local_metrics.performance.test.f1_score": {
                                "gte": 0.5
                            }
                        }
                    }
                )
            ]
        )
        agg2 = Agg(from_=node_hierarchy_2, mapping={MAPPING_NAME: MAPPING_DETAIL})
        self.assertEqual(agg2.deepest_linear_bucket_agg, 'week')