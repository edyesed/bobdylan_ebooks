from __future__ import print_function
import sys
import os
here = os.path.dirname(os.path.realpath(__file__))
# load vendored directory
sys.path.append(os.path.join(here, "./vendored"))
# regular include stuff
import json
import boto3
import email
import requests
import re
import elasticsearch
from elasticsearch import RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import pymarkovchain
import twitter

from pprint import pprint
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64encode, b64decode
#
#import credstash
#credstash.DEFAULT_REGION = "us-west-2"

ES_HOST = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
TWITTER_CONSUMERKEY = os.environ.get('TWITTER_CONSUMERKEY', None)
TWITTER_SECRET = os.environ.get('TWITTER_SECRET')
TWITTER_ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
TWITTER_OWNER_ID = os.environ.get('TWITTER_OWNER_ID')


# Search es, and return the results. we need a minimum number of
# results for a reasonable chain
#
# However, if we don't have a reasonable number of results, we can search
# twitter for more text, and then build a markov out of whatever we have
#
def es_search(es=None, searchword=None, min_hits=10, search_type="match",
              fuck_it_well_do_it_live=False):
    if search_type == "match":
        # v1 query
        # searchbody = {"query": {"match": {"text": searchword}}}
        # v2 query
        # searchbody = { "size": 0,
        #               "query": {
        #                 "query_string": {
        #                     "query": searchword,
        #                     "analyze_wildcard": True
        #                 }
        #               }
        #             }
        # v3 query omgwtfbbq, ES can randomize the document selection??
        #    you'll want this if you get many hits on your search
        searchbody = {"query": {
            "function_score": {
                "query": {
                    "query_string": {
                        "query": searchword,
                        "analyze_wildcard": True
                    }
                },
                "boost": "5",
                "random_score": {},
                "boost_mode": "multiply"
            }
        }
        }
    else:
        searchbody = {"query": {"more_like_this": {"fields": [
                      "text"], "like": searchword, "min_term_freq": 1}}}
    results = es.search(index='songs', doc_type='bobdylan',
                        body=searchbody,
                        filter_path=['hits.total', 'hits.hits._source.text'])
    print("ES returned %s results" % results['hits']['total'])
    if results['hits']['total'] >= min_hits or fuck_it_well_do_it_live:
        results = es.search(index='songs', doc_type='bobdylan',
                            body=searchbody,
                            filter_path=['hits.total',
                                         'hits.hits._source.text'],
                            size=min_hits * 3)
        # size=results['hits']['total'])
        print("ES returned %s results this time" % results['hits']['total'])

        return results
    # Not enough hits. SEARCH AGAIN
    else:
        print("recurse into es_search")
        return es_search(es=es, searchword=searchword, min_hits=10, search_type="not_match", fuck_it_well_do_it_live=True)


def print_with_timestamp(*args):
    """
       Default printer is print
    """
    print(datetime.utcnow().isoformat(), *args)


def trim_to_140(text=None):
    if (len(text)) > 140:
        # split(" ") to preserve newlines
        text = " ".join(text.split(" ")[:-1])
        return trim_to_140(text=text)
    return text


def markov_response(es_results=None):
    #
    # pprint(es_results)
    if es_results['hits']['total'] == 0:
        # Poor us, not enough hits!
        return markov_response(es_results=results)
    #print("dumping ES results in markov_response")
    # print(json.dumps(es_results))
    mc = pymarkovchain.MarkovChain()
    for songwords in es_results['hits']['hits']:
        #print("training with text: %s" % (songwords['_source']['text']))
        mc.generateDatabase(songwords['_source']['text'], sentenceSep='\r\n')
    # concat four markovs together
    response_text = mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()

    # trim down to <= 140 chars
    response_text = trim_to_140(text=response_text)

    try:
        response_text = response_text.lowercase()
    except:
        # if we can't lowercase(), meh
        pass
    print("ACTUAL RESPONSE: %s:  %s" % (len(response_text), response_text))
    return(response_text)


def twitter_reply(reply_type="", 
                  reply_text="", 
                  reply_handle=None, 
                  latitude=None,
                  longitude=None,
                  r_api=None,
                  tweet_id=None):
    if r_api is None:
        api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                          consumer_secret=TWITTER_SECRET,
                          access_token_key=TWITTER_ACCESS_TOKEN,
                          access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    else:
        api = r_api
    if reply_type == "TWEET":
        print("Sending tweet : %s" % (reply_text))
        #if latitude is None or longitude is None:
        #    response = api.PostUpdate(reply_text)
        #else:
        response = api.PostUpdate(reply_text,
                                  latitude=latitude,
                                  longitude=longitude)
        print("Response from twitter API")
        print(response)
    pass


def send_tweet(event, context):
    #
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
        es.info()
    except Exception as e:
        print("FAILED TO TALK TO AMAZON ES, because %s" % (e))
        raise(e)

    results = es_search(es, searchword='*')
    # pprint(results)
    try:
        #
        markov = markov_response(es_results=results)
    except Exception as e:
        raise Exception("Failed response building as exception %s" % (e))

    # reply twitter API style
    if TWITTER_CONSUMERKEY is None or TWITTER_SECRET is None or TWITTER_ACCESS_TOKEN is None or TWITTER_ACCESS_TOKEN_SECRET is None:
        print("If you define these ENV vars, I can respond via twitter. TWITTER_CONSUMERKEY, TWITTER_SECRET, TWITTER_ACCESS_TOKEN,TWITTER_ACCESS_TOKEN_SECRET")
        return True
    else:
        #print("DOING TWITTER REPLY")
        #print("MARKOV RESPONSE IS %s" % ( markov))
        twitter_reply(reply_type="TWEET",
                      reply_text=markov)
        return True
