""" This module responds to notifications by polling the twitter api for notifications

It responds to both regular tweet and DM events, and responds to each in kind.

"""
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
# Import regular_tweet, included in this package
import regular_tweet

from pprint import pprint
from datetime import datetime
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
def es_search(es=None, searchword='*', min_hits=10, search_type="tags",
              fuck_it_well_do_it_live=False):
    # v3 query omgwtfbbq, ES can randomize the document selection??
    print("searching ES on %s" % ( searchword ))
    #    you'll want this if you get many hits on your search
    if search_type == "tags":
        searchbody = {"query": {"function_score": {"query": {"query_string": {"query": 'tags:"' + searchword + '"', "analyze_wildcard": True}}, "boost": "5", "random_score": {}, "boost_mode": "multiply"}}}
    else:
        searchbody = {"query": {"function_score": {"query": {"query_string": {"query": searchword, "analyze_wildcard": True}}, "boost": "5", "random_score": {}, "boost_mode": "multiply"}}}

    es_count = es.count(index="songs", doc_type='bobdylan', body=searchbody)
    print("ES returned %s" % es_count['count'])

    # If we got back less than two, just send back random nonsense
    if es_count['count'] < 2:
        return es_search(es=es, search_type="not_tags", min_hits=40)
    # We got back less than we wanted, or somebody said
    #  fuck_it_well_do_it_live, so give the people what they want
    if es_count['count'] <= min_hits or fuck_it_well_do_it_live:
        return es.search(index='songs',
                         doc_type='bobdylan',
                         body=searchbody,
                         filter_path=['hits.total',
                                      'hits.hits._source.text'],
                         size=min_hits)
    # Not enough hits. SEARCH AGAIN
    else:
        return es.search(index='songs',
                         doc_type='bobdylan',
                         body=searchbody,
                         filter_path=['hits.total',
                                      'hits.hits._source.text'],
                         size=min_hits)


def print_with_timestamp(*args):
    """
       Default printer is print
    """
    print(datetime.utcnow().isoformat(), *args)


def markov_response(es_results=None, max_len=280, reply_handle=None):
    # ok
    #print("MARKOV MARKOV MARKOV")
    # pprint(es_results)
    if reply_handle:
        response_text = "@{0} ".format(reply_handle)
    else:
        response_text = ""
    if es_results['hits']['total'] == 0:
        # Poor us, not enough hits!
        return markov_response(es_results=es_results)
    mc = pymarkovchain.MarkovChain()
    for songwords in es_results['hits']['hits']:
        #print("training with text: %s" % (songwords['_source']['text']))
        mc.generateDatabase(songwords['_source']['text'], sentenceSep='\r\n')
    # concat four markovs together
    response_text += mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    #keepwords = regular_tweet.trim_to_280(text=response_text)
    keepwords = regular_tweet.trim_to_x(text=response_text, max_len=max_len)

    try:
        response_text = keepwords.lowercase()
    except:
        response_text = keepwords
    print("ACTUAL RESPONSE: %s:  %s" % (len(response_text),
                                        json.dumps(response_text)))
    return(response_text)


def twitter_reply(reply_type="", reply_text="", reply_handle=None, tweet_id=None):
    api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                      consumer_secret=TWITTER_SECRET,
                      access_token_key=TWITTER_ACCESS_TOKEN,
                      access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    if reply_type == "TWEET":
        print("TWEET ID I'M RESPONDING TO")
        print(tweet_id)
        response = api.PostUpdate(
            reply_text, in_reply_to_status_id=tweet_id)
        #response = api.PostUpdate(reply_text, in_reply_to_status_id=tweet_id)
        print("twitter response")
        print(response)
    if reply_type == "DM":
        print("DM HANDLE I'M RESPONDING TO")
        print(reply_handle)
        response = api.PostDirectMessage(
            screen_name=reply_handle, text=reply_text)
        print("twitter response")
        print(response)
    pass


def respond(event, context):
    """ 
        Now we're invoked on a schedule, and using the twitter api to 
          get notifications, and respond
    """
    try:
        api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                          consumer_secret=TWITTER_SECRET,
                          access_token_key=TWITTER_ACCESS_TOKEN,
                          access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    except Exception as e:
        print_with_timestamp("Failed to connect to twitter api: {0}".format(e))

    # 
    try:
        # First, attempt to talk to AWS Elasticsearch
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
        # In the event that we couldn't talk to AWS ES, try connecting
        #   without all those majicks
        print("Failed to connect to AWS Elasticsearch with : %s" % (e))
        print("Now connecting to regular elasticsearch")
        es = elasticsearch.Elasticsearch(hosts=[ES_HOST])
   

    # 
    # Query, find the highest notification id
    # 
    mentions = False
    max_id = False
    try:
        # pylint: disable=E1123
        res = es.search(index='mentions', 
                        doc_type='bobdylan_ebooks', 
                        body={"query": {"match_all": {}}, 
                              "sort": [{"id": "desc"}]
                             },
                        filter_path=['hits.total','hits.hits._source.id'])
        if len(res['hits']['hits']) > 0:
            # stuff was in elasticsearch, start from highest id
            max_id = res['hits']['hits'][0]['_source']['id']
            print("Max id of notification from ES was {0}".format(max_id))
        else:
            print_with_timestamp("Nothing in elasticsearch")
            # get 10 mentions from twitter
    except elasticsearch.exceptions.NotFoundError:
        # 
        # index does not exist, get mentions and create it
        # 
        mentions = api.GetMentions(count=10)
        for mention in mentions:
             es.index(index='mentions',
                      doc_type='bobdylan_ebooks',
                      id=mention.AsDict()['id'],
                      body=mention.AsDict())
    
    if mentions is False:
        if max_id is not False:
            # get up to 25 mentions since the last gotten mention
            mentions = api.GetMentions(since_id=max_id, count=25)
        else:
            print("NO IDEA. mentions was false, and no max_id")
            return False

    if len(mentions) is 0:
        print("There we no new mentions.")
        return True

    for mention in mentions:
        ## Find what they asked about, remove handles
        input_text = re.sub(r"\s+@\S+", "", mention.text)
        results = es_search(es,
                            searchword=input_text,
                            search_type="regular")
        try:
            markov = markov_response(es_results=results, 
                                     reply_handle=mention.user.screen_name)
        except Exception as e:
            raise Exception("Failed response building as exception %s" % (e))
        print("DOING TWITTER REPLY")
        print(json.dumps(
                  "reply_id:{0} handle:{1} len:{2} text:{3}".format(
                      mention.id,
                      mention.user.screen_name,
                      len(markov),
                      markov)))
        twitter_reply(reply_type="TWEET",
                      reply_text=markov,
                      reply_handle="@" + mention.user.screen_name,
                      tweet_id=mention.id)
        es.index(index='mentions',
                 doc_type='bobdylan_ebooks',
                 id=mention.AsDict()['id'],
                 body=mention.AsDict())
    
      
    return True

