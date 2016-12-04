#!/usr/bin/env python
#
# I learned about Algorithmia after scanning bobdylan.com 
# it seemed silly to go back there to get data that wasn't going to change
#  so here's an upserter 
#
import Algorithmia
import os
from elasticsearch import Elasticsearch
from pprint import pprint
import time

ES_URL = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200/')
ALGO_KEY = os.environ.get('ALGORITHMIA_KEY', None)


def get_documents(es=None, index=None, doc_type=None, count=0):
    return es.search(index=index, doc_type=doc_type, size=count, q='*')

if __name__ == "__main__":
    if ALGO_KEY is None:
        raise Exception('No ALGORITHMIA_KEY environment variable')
    es = Elasticsearch([ES_URL])
    algo_client = Algorithmia.client(ALGO_KEY)
    algo = algo_client.algo('nlp/AutoTag/1.0.0')
    doc_count = es.count(index='songs', doc_type='bobdylan', q='*')
    songs = get_documents(es=es, index='songs',
                          doc_type='bobdylan', count=doc_count['count'])
    for song in songs['hits']['hits']:
        print("Doing song %s" % ( song['_source']['title']))
        lyrics = song['_source']['text']
        tags = algo.pipe(lyrics.encode('utf-8'))
        es.update(index='songs', doc_type='bobdylan', id=song['_id'],
                  body={"doc": {'tags': tags.result}})
