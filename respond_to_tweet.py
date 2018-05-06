""" This module responds to notifications-of-tweets-that-come-in-via-email with tweets

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


class ParseHtml(object):

    """
       Make a html parser, and give us just the facts for our needs
       title, and a dataframe ( optionally contains headers )
    """

    def __init__(self, html=None):
        self.soup = BeautifulSoup(html, 'html.parser')
        # print(self.soup.prettify())

    def find_message_type(self):
        # dang ol' twitter. formatting emails with <table>
        thistype = None
        if thistype is None:
            self.tables = self.soup.find_all('td', {"class": "dm_text"})
            if self.tables:
                thistype = "DM"

        if thistype is None:
            self.tables = self.soup.find_all('td', {"class": "tweet_detail"})
            if self.tables:
                thistype = "TWEET"

        if thistype is None:
            print("Failed to find the type for this tweet")
            all_tds = self.soup.find_all('td')
            for td in all_tds:
                print("TDTDTDTD %s -> %s" % (td.__dict__, td.text))

        if thistype is None:
            print("FAILED TO UNDERSTAND THIS MESSAGE")
            print("DUMPING SOUP")
            print(self.soup.prettify())
            print("DUMPED SOUP")
        return thistype

    def give_text(self):
        return self.tables[0].text

    def find_tweetid(self):
        for a in self.soup.find_all('a'):
            tweet_id = re.search(r'%26tweet_id%3D(?P<tid>.*?)%26', a['href'])
            if tweet_id:
                print(a['href'])
                print(tweet_id.group('tid'))
                return tweet_id.group('tid')

    def find_sender_handle(self):
        if self.find_message_type() == "TWEET":
            for a in self.soup.find_all('a', {"class": "user_name"}):
                return(a.text)

        if self.find_message_type() == "DM":
            for td in self.soup.find_all('td', {"class": "preheader"}):
                return " ".join(re.findall("@[^:]+", td.text))

        return ""


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


def markov_response(es_results=None, max_len=280):
    # ok
    #print("MARKOV MARKOV MARKOV")
    # pprint(es_results)
    if es_results['hits']['total'] == 0:
        # Poor us, not enough hits!
        return markov_response(es_results=es_results)
    mc = pymarkovchain.MarkovChain()
    for songwords in es_results['hits']['hits']:
        #print("training with text: %s" % (songwords['_source']['text']))
        mc.generateDatabase(songwords['_source']['text'], sentenceSep='\r\n')
    # concat four markovs together
    response_text = mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    response_text += "\n" + mc.generateString()
    keepwords = regular_tweet.trim_to_280(text=response_text)

    try:
        response_text = keepwords.lowercase()
    except:
        response_text = keepwords
    print("ACTUAL RESPONSE: %s:  %s" % (len(response_text), response_text))
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
            reply_text + " " + reply_handle, in_reply_to_status_id=tweet_id)
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


def responder(event, context):
    try:
        message = json.loads(event['Records'][0]['Sns']['Message'])
        content = message['content']
        #print_with_timestamp('Message became ', json.dumps(message))
        #print_with_timestamp('Content became ', json.dumps(content))
    except Exception as e:
        print("There was some error ( %s ) loading message and/or content" % (e))
        message = event['Records'][0]['Sns']['Message']
        # print_with_timestamp('Message became ', message)
        # print_with_timestamp('Content became ', content)

    # make an email.parser out of the content of the message ( hopefully it's
    # multipart )
    #print_with_timestamp('CONTEXT ', dir(context))
    try:
        parsed_message = email.message_from_string(content)
        # xx print(parsed_message['to'])
        # xx print(parsed_message['from'])
    except:
        print_with_timestamp(
            "Failed to parse the content of the message: %s" % (content))
        return False

    # Now we have to decode the html text in the email
    email_content_decoded = None
    if parsed_message.is_multipart():
        for part in parsed_message.walk():
            ctype = part.get_content_type()
            #cdispo = str(part.get('Content-Disposition'))
            if ctype == 'text/html':
                #print("YES FOUND HTML")
                email_content_decoded = part.get_payload(decode=True)
    else:
        print_with_timestamp("message was not multipart")

    # Get a beautifulsoup parser for the now decoded html in the email
    bsp = ParseHtml(email_content_decoded)

    # Log if you get a tweet type that you cannot grok
    if bsp.find_message_type() is None:
        print_with_timestamp("Did not understand this event")
        print(json.dumps(event))
        print("BSP BSP BSP BSP")
        print(bsp)
        print("DIR bsp")
        print(dir(bsp))
        raise Exception("Did not grok")

    #print("BSP.find_message_type is now %s" % (bsp.find_message_type()))
    #print("BSP.give_text is now %s" % (bsp.give_text()))

    # Build a search string for elasticsearch by
    # removing the @handle in the originating message
    #
    search_text = re.sub(r"\s+@\S+", "", bsp.give_text())
    # And make a variable  of the originating handling
    respond_handle = bsp.find_sender_handle()
    print("RESPOND HANDLES ARE : %s" % (respond_handle))
    print("INPUT TWEET WAS: %s" % (search_text))
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
        es = elasticsearch.Elasticsearch(hosts=[ES_HOST])

    # Get matching lyrics
    # XXX
    results = es_search(es, searchword=search_text)
    # pprint(results)

    try:
        markov = markov_response(es_results=results)
    except Exception as e:
        raise Exception("Failed response building as exception %s" % (e))

    # reply twitter API style
    if TWITTER_CONSUMERKEY is None or TWITTER_SECRET is None or TWITTER_ACCESS_TOKEN is None or TWITTER_ACCESS_TOKEN_SECRET is None:
        print("If you define these ENV vars, I can respond via twitter. TWITTER_CONSUMERKEY, TWITTER_SECRET, TWITTER_ACCESS_TOKEN,TWITTER_ACCESS_TOKEN_SECRET")
        return True
    else:
        print("DOING TWITTER REPLY")
        twitter_reply(reply_type=bsp.find_message_type(),
                      reply_text=markov,
                      reply_handle=respond_handle,
                      tweet_id=bsp.find_tweetid())
        return True
