"""
Accept incoming calls, and say back a @bobdylan_ebooks pontification

"""
from __future__ import print_function
import sys
import os
here = os.path.dirname(os.path.realpath(__file__))
# load vendored directory
sys.path.append(os.path.join(here, "./vendored"))

# regular include stuff
import json
import datetime
import boto3
import re
import elasticsearch
import pymarkovchain
import regular_tweet
import twitter

from elasticsearch import RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from twilio import twiml
from urlparse import parse_qs
from notifications import es_search
from notifications import markov_response
from geopy.geocoders import Nominatim
#from pprint import pprint
#from datetime import datetime

ES_HOST = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
TWITTER_CONSUMERKEY = os.environ.get('TWITTER_CONSUMERKEY', None)
TWITTER_SECRET = os.environ.get('TWITTER_SECRET')
TWITTER_ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
TWITTER_OWNER_ID = os.environ.get('TWITTER_OWNER_ID')

api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                  consumer_secret=TWITTER_SECRET,
                  access_token_key=TWITTER_ACCESS_TOKEN,
                  access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)

def endpoint(event, context):
    ### the incoming request(event) has a field called 'body' where the relevant
    ### info appears formatted as a querystring
    try:
        parsed_body = parse_qs(event['body'])
    except AttributeError:
        # due to $reasons, this comes in as a dict.
        parsed_body = event['body']
    print("Call from")
    print(parsed_body)

    # connect to ES
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

    results = es_search(es, search_type="regular")
    words_to_say = markov_response(es_results=results, max_len=135)

    resp = twiml.Response()
    resp.say(words_to_say)
    print(str(resp).replace("\n", " "))
    # tweet our response
    if parsed_body['FromCity'] and parsed_body['FromState'] and parsed_body['FromCountry'] and parsed_body['FromZip']:
        geolocator = Nominatim()
        geostring = "{0}, {1}, {2} {3}".format(parsed_body['FromCity'],
                                               parsed_body['FromState'],
                                               parsed_body['FromCountry'],
                                               parsed_body['FromZip'])
        location = geolocator.geocode(geostring)
        regular_tweet.twitter_reply(reply_type="TWEET",
                                    reply_text=u"\u260E" + " " + words_to_say,
                                    longitude=location.longitude,
                                    latitude=location.latitude,
                                    r_api=api) 
    else:
        print("Could not attach location")
        regular_tweet.twitter_reply(reply_type="TWEET",
                                    reply_text=u"\u260E" + " " + words_to_say,
                                    r_api=api) 
     
    return str(resp)
   
