#!/usr/bin/env python
import os
import boto3
import elasticsearch
from elasticsearch import RequestsHttpConnection
from requests_aws4auth import AWS4Auth

DB_URL = os.environ.get('DYNAMODB_URL', 'http://localhost:8000')
ES_HOST = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')


try:
    cred = boto3.session.Session().get_credentials()
    awsauth = AWS4Auth(cred.access_key,
                       cred.secret_key,
                       os.environ.get('AWS_DEFAULT_REGION'),
                       'es',
                       session_token=cred.token)
    es = elasticsearch.Elasticsearch(
            hosts=[ES_HOST],
            connection_class=elasticsearch.RequestsHttpConnection,
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True)
    #print("ES INFO ES INFO ES INFO")
    # print(es.info())
    es.info()
except Exception as e:
    raise(e)


#dynamodb = boto3.resource('dynamodb', endpoint_url=DB_URL)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('bobdylan_songs')

es_songs = es.search(index='songs', doc_type='bobdylan', body={"query": {"match_all": {}}}, size=700)

#table.put_item(Item={'title': 'anything',
#                     'id': 'xyz',
#                     'songinfo': {'a': 'B', 'thing': [], 'aname': ''}
#                    })


for song in es_songs['hits']['hits']:
    #print("{0} -> {1}".format('bobdylan', song['_source']['title'].encode()))
    print("{0} -> {1}".format('bobdylan', song['_id']))
    if not song['_source']['text']:
        continue
    if not song['_source']['credit']:
        song['_source']['credit'] = 'UnAttributed'
    if not song['_source']['album']:
        song['_source']['album'] = 'NoAlbum'
    try:
        table.put_item(Item={'title': song['_source']['title'],
                             'id': song['_id'],
                             'songinfo': song['_source']
                            })
    except Exception as e:
        print("{0} -> {1} -> {2}".format(song['_id'], song['_source']['title'], song['_source']))
        print(e)
        print(dir(e))
        raise(e)
    

#table = dynamodb.create_table(
#            TableName='songs',
#            KeySchema=[{'AttributeName': 'artist', 'KeyType': 'HASH'},
#                       {'AttributeName': 'title', 'KeyType': 'RANGE'} ],
#            AttributeDefinitions=[
#                       {'AttributeName': 'artist', 'AttributeType': 'S'},
#                       {'AttributeName': 'title', 'AttributeType': 'S' }],
#            ProvisionedThroughput={'ReadCapacityUnits': 10,
#                                   'WriteCapacityUnits': 10}
#        )
