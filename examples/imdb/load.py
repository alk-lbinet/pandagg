import json
from os.path import join
from elasticsearch import Elasticsearch, helpers
from examples.imdb.conf import ES_HOST, DATA_DIR
from pandagg.mapping import (
    Mapping,
    Keyword,
    Text,
    Float,
    Nested,
    Integer,
)

index_name = "movies"
mapping = Mapping(
    properties=[
        Keyword("movie_id"),
        Text("name", fields=Keyword("raw")),
        Integer("year"),
        Float("rank"),
        Keyword("genres"),
        Nested(
            "roles",
            properties=[
                Keyword("role"),
                Keyword("actor_id"),
                Keyword("gender"),
                Text("first_name", fields=Keyword("raw")),
                Text("last_name", fields=Keyword("raw")),
                Text("full_name", fields=Keyword("raw")),
            ],
        ),
        Nested(
            "directors",
            properties=[
                Keyword("role"),
                Keyword("director_id"),
                Keyword("gender"),
                Text("first_name", fields=Keyword("raw")),
                Text("last_name", fields=Keyword("raw")),
                Text("full_name", fields=Keyword("raw")),
            ],
        ),
        Integer("nb_directors"),
        Integer("nb_roles"),
    ]
).to_dict()


def bulk_index(client, docs):
    helpers.bulk(
        client=client,
        actions=[
            {
                "_index": index_name,
                "_op_type": "index",
                "_id": document["movie_id"],
                "_source": document,
            }
            for document in docs
        ],
    )


if __name__ == "__main__":
    es_client = Elasticsearch(hosts=[ES_HOST])

    if es_client.indices.exists(index=index_name):
        print("-" * 50)
        print("DELETE INDEX\n")
        es_client.indices.delete(index=index_name)

    print("-" * 50)
    print("CREATE INDEX\n")
    es_client.indices.create(index_name)
    print("-" * 50)
    print("UPDATE MAPPING\n")
    es_client.indices.put_mapping(index=index_name, body=mapping)

    print("-" * 50)
    print("WRITE DOCUMENTS\n")
    docs_buffer = []
    with open(join(DATA_DIR, "serialized.json"), "r") as f:
        for l in f.readlines():
            if len(docs_buffer) >= 100:
                bulk_index(es_client, docs_buffer)
                docs_buffer = []
            s = json.loads(l)
            docs_buffer.append(s)
    if docs_buffer:
        bulk_index(es_client, docs_buffer)

    es_client.indices.refresh(index=index_name)
