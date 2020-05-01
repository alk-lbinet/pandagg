#!/usr/bin/env python
# -*- coding: utf-8 -*-

# =============================================================================
#                                   IMPORTS
# =============================================================================

from unittest import TestCase
from lighttree.exceptions import MultipleRootError, NotFoundNodeError
from mock import patch

from pandagg.tree.aggs import Aggs
from pandagg.exceptions import (
    AbsentMappingFieldError,
    InvalidOperationMappingFieldError,
)
from pandagg.tree.mapping import Mapping
from pandagg.node.aggs.bucket import DateHistogram, Terms, Filter
from pandagg.node.aggs.metric import Avg, Min

import tests.testing_samples.data_sample as sample

from tests.testing_samples.mapping_example import MAPPING


def to_id_set(nodes):
    return {n.identifier for n in nodes}


class AggTestCase(TestCase):
    def setUp(self):
        patcher = patch("uuid.uuid4", side_effect=range(1000))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deserialize_nodes_with_subaggs(self):
        expected = {
            "genres": {
                "terms": {"field": "genres", "size": 3},
                "aggs": {
                    "movie_decade": {
                        "date_histogram": {"field": "year", "fixed_interval": "3650d"}
                    }
                },
            }
        }
        agg1 = Aggs(expected)
        agg2 = Aggs(
            Terms(
                "genres",
                field="genres",
                size=3,
                aggs=DateHistogram(
                    name="movie_decade", field="year", fixed_interval="3650d"
                ),
            )
        )
        agg3 = Aggs(
            Terms(
                "genres",
                field="genres",
                size=3,
                aggs=[
                    DateHistogram(
                        name="movie_decade", field="year", fixed_interval="3650d"
                    )
                ],
            )
        )
        agg4 = Aggs(
            Terms(
                "genres",
                field="genres",
                size=3,
                aggs={
                    "movie_decade": {
                        "date_histogram": {"field": "year", "fixed_interval": "3650d"}
                    }
                },
            )
        )
        agg5 = Aggs(
            {
                "genres": {
                    "terms": {"field": "genres", "size": 3},
                    "aggs": DateHistogram(
                        name="movie_decade", field="year", fixed_interval="3650d"
                    ),
                }
            }
        )
        for a in (agg1, agg2, agg3, agg4, agg5):
            self.assertEqual(a.to_dict(), expected)

    def test_add_node_with_mapping(self):
        with_mapping = Aggs(mapping=MAPPING)
        self.assertEqual(len(with_mapping.list()), 0)

        # add regular node
        with_mapping.insert_node(Terms("workflow", field="workflow"))
        self.assertEqual(len(with_mapping.list()), 1)

        # try to add second root fill fail
        with self.assertRaises(MultipleRootError):
            with_mapping.insert_node(
                Terms("classification_type", field="classification_type")
            )

        # try to add field aggregation on non-existing field will fail
        with self.assertRaises(AbsentMappingFieldError):
            with_mapping.insert_node(
                node=Terms("imaginary_agg", field="imaginary_field"),
                parent_id="workflow",
            )
        self.assertEqual(len(with_mapping.list()), 1)

        # try to add aggregation on a non-compatible field will fail
        with self.assertRaises(InvalidOperationMappingFieldError):
            with_mapping.insert_node(
                node=Avg("average_of_string", field="classification_type"),
                parent_id="workflow",
            )
        self.assertEqual(len(with_mapping.list()), 1)

        # add field aggregation on field passing through nested will automatically add nested
        with_mapping.insert_node(
            node=Avg("local_f1_score", field="local_metrics.performance.test.f1_score"),
            parent_id="workflow",
        )
        self.assertEqual(len(with_mapping.list()), 3)
        self.assertEqual(
            with_mapping.__str__(),
            """<Aggregation>
[workflow] terms
└── [nested_below_workflow] nested
    └── [local_f1_score] avg
""",
        )
        self.assertIn("nested_below_workflow", with_mapping)
        nested_node = with_mapping.get("nested_below_workflow")
        self.assertEqual(nested_node.KEY, "nested")
        self.assertEqual(nested_node.path, "local_metrics")

        # add other agg requiring nested will reuse nested agg as parent
        with_mapping.insert_node(
            node=Avg(
                "local_precision", field="local_metrics.performance.test.precision"
            ),
            parent_id="workflow",
        )
        self.assertEqual(
            with_mapping.__str__(),
            """<Aggregation>
[workflow] terms
└── [nested_below_workflow] nested
    ├── [local_f1_score] avg
    └── [local_precision] avg
""",
        )
        self.assertEqual(len(with_mapping.list()), 4)

        # add under a nested parent a field aggregation that requires to be located under root will automatically
        # add reverse-nested
        with_mapping.insert_node(
            node=Terms("language_terms", field="language"),
            parent_id="nested_below_workflow",
        )
        self.assertEqual(len(with_mapping.list()), 6)
        self.assertEqual(
            with_mapping.__str__(),
            """<Aggregation>
[workflow] terms
└── [nested_below_workflow] nested
    ├── [local_f1_score] avg
    ├── [local_precision] avg
    └── [reverse_nested_below_nested_below_workflow] reverse_nested
        └── [language_terms] terms
""",
        )

    def test_add_node_without_mapping(self):
        without_mapping = Aggs()
        self.assertEqual(len(without_mapping.list()), 0)

        # add regular node
        without_mapping.insert_node(
            Terms("workflow_not_existing", field="field_not_existing")
        )
        self.assertEqual(len(without_mapping.list()), 1)

    # TODO - finish these tests (reverse nested)
    def test_paste_tree_with_mapping(self):
        # with explicit nested
        initial_agg_1 = Aggs(
            {
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w",
                    }
                }
            },
            mapping=MAPPING,
        )
        self.assertEqual(to_id_set(initial_agg_1.list()), {"week"})
        pasted_agg_1 = Aggs(
            {
                "nested_below_week": {
                    "nested": {"path": "local_metrics"},
                    "aggs": {
                        "local_metrics.field_class.name": {
                            "terms": {
                                "field": "local_metrics.field_class.name",
                                "size": 10,
                            }
                        }
                    },
                }
            }
        )
        self.assertEqual(
            to_id_set(pasted_agg_1.list()),
            {"nested_below_week", "local_metrics.field_class.name"},
        )

        initial_agg_1.insert_tree(pasted_agg_1, "week")
        self.assertEqual(
            to_id_set(initial_agg_1.list()),
            {"week", "nested_below_week", "local_metrics.field_class.name"},
        )
        self.assertEqual(
            initial_agg_1.__str__(),
            """<Aggregation>
[week] date_histogram
└── [nested_below_week] nested
    └── [local_metrics.field_class.name] terms
""",
        )

        # without explicit nested
        initial_agg_2 = Aggs(
            {
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w",
                    }
                }
            },
            mapping=MAPPING,
        )
        self.assertEqual(to_id_set(initial_agg_2.list()), {"week"})
        pasted_agg_2 = Aggs(
            {
                "local_metrics.field_class.name": {
                    "terms": {"field": "local_metrics.field_class.name", "size": 10}
                }
            }
        )
        self.assertEqual(
            to_id_set(pasted_agg_2.list()), {"local_metrics.field_class.name"}
        )

        initial_agg_2.insert_tree(pasted_agg_2, "week")
        self.assertEqual(
            to_id_set(initial_agg_2.list()),
            {"week", "nested_below_week", "local_metrics.field_class.name"},
        )
        self.assertEqual(
            initial_agg_2.__str__(),
            """<Aggregation>
[week] date_histogram
└── [nested_below_week] nested
    └── [local_metrics.field_class.name] terms
""",
        )

    def test_insert_tree_without_mapping(self):
        # with explicit nested
        initial_agg_1 = Aggs(
            {
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w",
                    }
                }
            },
            mapping=None,
        )
        self.assertEqual({n.identifier for n in initial_agg_1.list()}, {"week"})

        pasted_agg_1 = Aggs(
            {
                "nested_below_week": {
                    "nested": {"path": "local_metrics"},
                    "aggs": {
                        "local_metrics.field_class.name": {
                            "terms": {
                                "field": "local_metrics.field_class.name",
                                "size": 10,
                            }
                        }
                    },
                }
            }
        )
        self.assertEqual(
            to_id_set(pasted_agg_1.list()),
            {"nested_below_week", "local_metrics.field_class.name"},
        )

        initial_agg_1.insert_tree(pasted_agg_1, "week")
        self.assertEqual(
            to_id_set(initial_agg_1.list()),
            {"week", "nested_below_week", "local_metrics.field_class.name"},
        )
        self.assertEqual(
            initial_agg_1.__str__(),
            """<Aggregation>
[week] date_histogram
└── [nested_below_week] nested
    └── [local_metrics.field_class.name] terms
""",
        )

        # without explicit nested (will NOT add nested)
        initial_agg_2 = Aggs(
            {
                "week": {
                    "date_histogram": {
                        "field": "date",
                        "format": "yyyy-MM-dd",
                        "interval": "1w",
                    }
                }
            },
            mapping=None,
        )
        self.assertEqual(to_id_set(initial_agg_2.list()), {"week"})

        pasted_agg_2 = Aggs(
            {
                "local_metrics.field_class.name": {
                    "terms": {"field": "local_metrics.field_class.name", "size": 10}
                }
            }
        )
        self.assertEqual(
            to_id_set(pasted_agg_2.list()), {"local_metrics.field_class.name"}
        )

        initial_agg_2.insert_tree(pasted_agg_2, "week")
        self.assertEqual(
            to_id_set(initial_agg_2.list()), {"week", "local_metrics.field_class.name"}
        )
        self.assertEqual(
            initial_agg_2.__str__(),
            """<Aggregation>
[week] date_histogram
└── [local_metrics.field_class.name] terms
""",
        )

    def test_interpret_agg_string(self):
        some_agg = Aggs()
        some_agg = some_agg.aggs("some_field", insert_below=None)
        self.assertEqual(
            some_agg.to_dict(), {"some_field": {"terms": {"field": "some_field"}}}
        )

        # with default size
        some_agg = Aggs()
        some_agg = some_agg.aggs("some_field", insert_below=None, size=10)
        self.assertEqual(
            some_agg.to_dict(),
            {"some_field": {"terms": {"field": "some_field", "size": 10}}},
        )

        # with parent
        some_agg = Aggs(
            {"root_agg_name": {"terms": {"field": "some_field", "size": 5}}}
        )
        some_agg = some_agg.aggs("child_field", insert_below="root_agg_name")
        self.assertEqual(
            some_agg.to_dict(),
            {
                "root_agg_name": {
                    "aggs": {"child_field": {"terms": {"field": "child_field"}}},
                    "terms": {"field": "some_field", "size": 5},
                }
            },
        )

        # with required nested
        some_agg = Aggs(
            {"term_workflow": {"terms": {"field": "workflow", "size": 5}}},
            mapping=MAPPING,
        )
        some_agg = some_agg.aggs(
            "local_metrics.field_class.name", insert_below="term_workflow"
        )
        self.assertEqual(
            some_agg.to_dict(),
            {
                "term_workflow": {
                    "aggs": {
                        "nested_below_term_workflow": {
                            "aggs": {
                                "local_metrics.field_class.name": {
                                    "terms": {"field": "local_metrics.field_class.name"}
                                }
                            },
                            "nested": {"path": "local_metrics"},
                        }
                    },
                    "terms": {"field": "workflow", "size": 5},
                }
            },
        )

    def test_interpret_node(self):
        node = Terms(name="some_name", field="some_field", size=10)
        some_agg = Aggs().aggs(node, insert_below=None)
        self.assertEqual(
            some_agg.to_dict(),
            {"some_name": {"terms": {"field": "some_field", "size": 10}}},
        )
        # with parent with required nested
        some_agg = Aggs(
            {"term_workflow": {"terms": {"field": "workflow", "size": 5}}},
            mapping=MAPPING,
        )
        node = Avg(name="min_local_f1", field="local_metrics.performance.test.f1_score")
        some_agg = some_agg.aggs(node, insert_below="term_workflow")
        self.assertEqual(
            some_agg.to_dict(),
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
                            "nested": {"path": "local_metrics"},
                        }
                    },
                    "terms": {"field": "workflow", "size": 5},
                }
            },
        )

    def test_query_dict(self):
        # empty
        self.assertEqual(Aggs().to_dict(), {})

        # single node
        agg = Aggs()
        node = Terms(name="root_agg", field="some_field", size=10)
        agg.insert_node(node)
        self.assertEqual(
            agg.to_dict(), {"root_agg": {"terms": {"field": "some_field", "size": 10}}},
        )

        # hierarchy
        agg.insert_node(
            Terms(name="other_name", field="other_field", size=30), "root_agg"
        )
        agg.insert_node(
            Avg(name="avg_some_other_field", field="some_other_field"), "root_agg"
        )
        self.assertEqual(
            agg.__str__(),
            """<Aggregation>
[root_agg] terms
├── [avg_some_other_field] avg
└── [other_name] terms
""",
        )
        self.assertEqual(
            agg.to_dict(),
            {
                "root_agg": {
                    "aggs": {
                        "avg_some_other_field": {"avg": {"field": "some_other_field"}},
                        "other_name": {"terms": {"field": "other_field", "size": 30}},
                    },
                    "terms": {"field": "some_field", "size": 10},
                }
            },
        )

    def test_validate_aggs_parent_id(self):
        """
        <Aggregation>
        classification_type
        └── global_metrics.field.name
            ├── avg_f1_micro
            └── avg_nb_classes
        """
        my_agg = Aggs(sample.EXPECTED_AGG_QUERY, mapping=MAPPING)

        with self.assertRaises(ValueError) as e:
            my_agg._validate_aggs_parent_id(pid=None)
        self.assertEqual(
            e.exception.args,
            (
                "Declaration is ambiguous, you must declare the node id under which these "
                "aggregations should be placed.",
            ),
        )

        with self.assertRaises(ValueError) as e:
            my_agg._validate_aggs_parent_id("avg_f1_micro")
        self.assertEqual(
            e.exception.args, ("Node id <avg_f1_micro> is not a bucket aggregation.",)
        )

        self.assertEqual(
            my_agg._validate_aggs_parent_id("global_metrics.field.name"),
            "global_metrics.field.name",
        )

        with self.assertRaises(NotFoundNodeError) as e:
            my_agg._validate_aggs_parent_id("non-existing-node")
        self.assertEqual(
            e.exception.args, ("Node id <non-existing-node> doesn't exist in tree",)
        )

        # linear agg
        my_agg.drop_node("avg_f1_micro")
        my_agg.drop_node("avg_nb_classes")
        """
        <Aggregation>
        classification_type
        └── global_metrics.field.name
        """
        self.assertEqual(
            my_agg._validate_aggs_parent_id(None), "global_metrics.field.name"
        )

        # empty agg
        agg = Aggs()
        self.assertEqual(agg._validate_aggs_parent_id(None), None)

        # TODO - pipeline aggregation under metric agg

    def test_agg_method(self):
        pass

    def test_groupby_method(self):
        pass

    def test_mapping_from_init(self):
        agg_from_dict_mapping = Aggs(mapping=MAPPING)
        agg_from_tree_mapping = Aggs(mapping=Mapping(MAPPING))
        self.assertIsInstance(agg_from_dict_mapping, Aggs)
        self.assertIsInstance(agg_from_tree_mapping, Aggs)
        self.assertEqual(
            agg_from_dict_mapping.tree_mapping.__repr__(),
            agg_from_tree_mapping.tree_mapping.__repr__(),
        )
        self.assertEqual(
            agg_from_dict_mapping.to_dict(), agg_from_tree_mapping.to_dict()
        )

    def test_init_from_dict(self):
        my_agg = Aggs(sample.EXPECTED_AGG_QUERY, mapping=MAPPING)
        self.assertEqual(my_agg.to_dict(), sample.EXPECTED_AGG_QUERY)
        self.assertEqual(my_agg.__str__(), sample.EXPECTED_REPR)

    def test_init_from_node_hierarchy(self):
        node_hierarchy = sample.get_node_hierarchy()

        agg = Aggs(node_hierarchy, mapping=MAPPING)
        self.assertEqual(agg.to_dict(), sample.EXPECTED_AGG_QUERY)
        self.assertEqual(agg.__str__(), sample.EXPECTED_REPR)

        # with nested
        node_hierarchy = DateHistogram(
            name="week",
            field="date",
            interval="1w",
            aggs=[
                Terms(
                    name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                    aggs=[
                        Min(
                            name="min_f1_score",
                            field="local_metrics.performance.test.f1_score",
                        )
                    ],
                )
            ],
        )
        agg = Aggs(node_hierarchy, mapping=MAPPING)
        self.assertEqual(
            agg.to_dict(),
            {
                "week": {
                    "aggs": {
                        "nested_below_week": {
                            "aggs": {
                                "local_metrics.field_class.name": {
                                    "aggs": {
                                        "min_f1_score": {
                                            "min": {
                                                "field": "local_metrics.performance.test.f1_score"
                                            }
                                        }
                                    },
                                    "terms": {
                                        "field": "local_metrics.field_class.name",
                                        "size": 10,
                                    },
                                }
                            },
                            "nested": {"path": "local_metrics"},
                        }
                    },
                    "date_histogram": {"field": "date", "interval": "1w"},
                }
            },
        )
        self.assertEqual(
            agg.__str__(),
            """<Aggregation>
[week] date_histogram
└── [nested_below_week] nested
    └── [local_metrics.field_class.name] terms
        └── [min_f1_score] min
""",
        )

    def test_groupby_and_agg(self):
        agg = sample.get_wrapper_declared_agg()
        self.assertEqual(agg.to_dict(), sample.EXPECTED_AGG_QUERY)
        self.assertEqual(agg.__str__(), sample.EXPECTED_REPR)

    def test_groupby_insert_below(self):
        a1 = Aggs(
            Terms("A", field="A", aggs=[Terms("B", field="B"), Terms("C", field="C")])
        )
        self.assertEqual(
            a1.__repr__(),
            """<Aggregation>
[A] terms
├── [B] terms
└── [C] terms
""",
        )

        self.assertEqual(
            a1.groupby(Terms("D", field="D"), insert_below="A").__repr__(),
            """<Aggregation>
[A] terms
└── [D] terms
    ├── [B] terms
    └── [C] terms
""",
        )
        self.assertEqual(
            a1.groupby(
                [Terms("D", field="D"), Terms("E", field="E")], insert_below="A"
            ).__repr__(),
            """<Aggregation>
[A] terms
└── [D] terms
    └── [E] terms
        ├── [B] terms
        └── [C] terms
""",
        )
        self.assertEqual(
            a1.groupby(
                Terms("D", field="D", aggs=Terms("E", field="E")), insert_below="A"
            ).__repr__(),
            """<Aggregation>
[A] terms
└── [D] terms
    └── [E] terms
        ├── [B] terms
        └── [C] terms
""",
        )

    def test_groupby_insert_above(self):
        a1 = Aggs(
            Terms("A", field="A", aggs=[Terms("B", field="B"), Terms("C", field="C")])
        )
        self.assertEqual(
            a1.__repr__(),
            """<Aggregation>
[A] terms
├── [B] terms
└── [C] terms
""",
        )

        self.assertEqual(
            a1.groupby(Terms("D", field="D"), insert_above="B").__repr__(),
            """<Aggregation>
[A] terms
├── [C] terms
└── [D] terms
    └── [B] terms
""",
        )
        self.assertEqual(
            a1.groupby(
                [Terms("D", field="D"), Terms("E", field="E")], insert_above="B"
            ).__repr__(),
            """<Aggregation>
[A] terms
├── [C] terms
└── [D] terms
    └── [E] terms
        └── [B] terms
""",
        )
        self.assertEqual(
            a1.groupby(
                Terms("D", field="D", aggs=Terms("E", field="E")), insert_above="B"
            ).__repr__(),
            """<Aggregation>
[A] terms
├── [C] terms
└── [D] terms
    └── [E] terms
        └── [B] terms
""",
        )
        # above root
        self.assertEqual(
            a1.groupby(
                Terms("D", field="D", aggs=Terms("E", field="E")), insert_above="A"
            ).__repr__(),
            """<Aggregation>
[D] terms
└── [E] terms
    └── [A] terms
        ├── [B] terms
        └── [C] terms
""",
        )

    def test_agg_insert_below(self):
        a1 = Aggs(
            Terms("A", field="A", aggs=[Terms("B", field="B"), Terms("C", field="C")])
        )
        self.assertEqual(
            a1.__repr__(),
            """<Aggregation>
[A] terms
├── [B] terms
└── [C] terms
""",
        )

        self.assertEqual(
            a1.aggs(Terms("D", field="D"), insert_below="A").__repr__(),
            """<Aggregation>
[A] terms
├── [B] terms
├── [C] terms
└── [D] terms
""",
        )
        self.assertEqual(
            a1.aggs(
                [Terms("D", field="D"), Terms("E", field="E")], insert_below="A"
            ).__repr__(),
            """<Aggregation>
[A] terms
├── [B] terms
├── [C] terms
├── [D] terms
└── [E] terms
""",
        )

    def test_applied_nested_path_at_node(self):
        """ Check that correct nested path is detected at node levels:
        week
        └── nested_below_week
            └── local_metrics.field_class.name
                ├── avg_f1_score
                ├── max_f1_score
                └── min_f1_score
        """
        node_hierarchy = DateHistogram(
            name="week",
            field="date",
            interval="1w",
            aggs=[
                Terms(
                    name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                    aggs=[
                        Min(
                            name="min_f1_score",
                            field="local_metrics.performance.test.f1_score",
                        )
                    ],
                )
            ],
        )
        agg = Aggs(node_hierarchy, mapping=MAPPING)

        self.assertEqual(agg.applied_nested_path_at_node("week"), None)
        for nid in (
            "nested_below_week",
            "local_metrics.field_class.name",
            "min_f1_score",
        ):
            self.assertEqual(agg.applied_nested_path_at_node(nid), "local_metrics")

    def test_deepest_linear_agg(self):
        # deepest_linear_bucket_agg
        """
        week
        └── nested_below_week
            └── local_metrics.field_class.name   <----- HERE because then metric aggregation
                └── avg_f1_score
        """
        node_hierarchy = DateHistogram(
            name="week",
            field="date",
            interval="1w",
            aggs=[
                Terms(
                    name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                    aggs=[
                        Min(
                            name="min_f1_score",
                            field="local_metrics.performance.test.f1_score",
                        )
                    ],
                )
            ],
        )
        agg = Aggs(node_hierarchy, mapping=MAPPING)
        self.assertEqual(
            agg.deepest_linear_bucket_agg, "local_metrics.field_class.name"
        )

        # week is last bucket linear bucket
        node_hierarchy_2 = DateHistogram(
            name="week",
            field="date",
            interval="1w",
            aggs=[
                Terms(
                    name="local_metrics.field_class.name",
                    field="local_metrics.field_class.name",
                    size=10,
                ),
                Filter(
                    name="f1_score_above_threshold",
                    filter={
                        "range": {
                            "local_metrics.performance.test.f1_score": {"gte": 0.5}
                        }
                    },
                ),
            ],
        )
        agg2 = Aggs(node_hierarchy_2, mapping=MAPPING)
        self.assertEqual(agg2.deepest_linear_bucket_agg, "week")
