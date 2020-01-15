from pandagg.base.node.query import CompoundClause
from pandagg.base.node.query._parameter_clause import Organic, QueryP


class ScriptScore(CompoundClause):
    DEFAULT_OPERATOR = QueryP
    PARAMS_WHITELIST = ['query', 'script', 'min_score']
    KEY = 'script_score'


class PinnedQuery(CompoundClause):
    DEFAULT_OPERATOR = Organic
    PARAMS_WHITELIST = ['ids', 'organic']
    KEY = 'pinned'


SPECIALIZED_COMPOUND_QUERIES = [
    ScriptScore,
    PinnedQuery
]