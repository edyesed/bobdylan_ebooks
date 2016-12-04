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

class ParseHtml(object):

    """
       Make a html parser, and give us just the facts for our needs
       title, and a dataframe ( optionally contains headers )
    """

    def __init__(self, html=None):
        self.soup = BeautifulSoup(html, 'html.parser')
        #print(self.soup.prettify())
   
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
                print("TDTDTDTD %s -> %s" % ( td.__dict__, td.text))

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
def es_search(es=None, searchword=None, min_hits=10, search_type="match",
              fuck_it_well_do_it_live=False):
     if search_type == "match":
         # v1 query
         # searchbody = {"query": {"match": {"text": searchword}}}
         # v2 query
         #searchbody = { "size": 0,
         #               "query": {
         #                 "query_string": {
         #                     "query": searchword,
         #                     "analyze_wildcard": True
         #                 }
         #               }
         #             }
         # v3 query omgwtfbbq, ES can randomize the document selection??
         #    you'll want this if you get many hits on your search
         searchbody = { "query": {
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
     results = es.search(index="songs", body=searchbody,
                         filter_path=['hits.total', 'hits.hits._source.text'])
     #print("ES returned %s" % results['hits']['total'])
     if results['hits']['total'] >= min_hits or fuck_it_well_do_it_live:
          results =  es.search(index="songs", body=searchbody,
                         filter_path=['hits.total', 'hits.hits._source.text'])
     print("ES returned %s" % results['hits']['total'])
     if results['hits']['total'] >= min_hits or fuck_it_well_do_it_live:
          results =  es.search(index="songs", body=searchbody,
                                   filter_path=['hits.total',
                                                'hits.hits._source.text'],
                                   size=min_hits*3)
                                   #size=results['hits']['total'])

          return results
     # Not enough hits. SEARCH AGAIN
     else:
         print("going back in")
         return es_search(es=es, searchword=searchword, min_hits=10, search_type="not_match", fuck_it_well_do_it_live=True)
        

def print_with_timestamp(*args):
    """
       Default printer is print
    """
    print(datetime.utcnow().isoformat(), *args)


def markov_response(es_results=None, max_len=140):
    # ok
    #print("MARKOV MARKOV MARKOV")
    #pprint(es_results)
    if es_results['hits']['total'] == 0:
        # Poor us, not enough hits!
        return markov_response(es_results=results)
    mc = pymarkovchain.MarkovChain()
    for songwords in es_results['hits']['hits']:
        #print("training with text: %s" % (songwords['_source']['text']))
        mc.generateDatabase(songwords['_source']['text'], sentenceSep='\r\n')
    # concat four markovs together
    response_text = mc.generateString()
    response_text += " " + mc.generateString()
    response_text += " " + mc.generateString()
    response_text += " " + mc.generateString()
    #response_text = mc.generateStringWithSeed(searchword)
    #print("Response would be:\n%s\n" % (response_text))
    max_tweet_len = max_len
    keepwords = ""
    if len(response_text) > max_tweet_len:
       words = response_text.split()
       for word in words:
          #print("KEEPWORDS: %s " % (keepwords))
          if len(keepwords) >140:
              raise Exception("Too long of a response")
              break
          if len(keepwords) + len(word) > 140:
              # RETURN NOW THIS IS ENOUGH
              break
          keepwords = keepwords + " " + word
    else:
       keepwords = response_text
    #print("ACTUAL RESPONSE: %s" % ( len(keepwords)))
    try:
        response_text = keepwords.lowercase()
    except:
        response_text = keepwords
    print("ACTUAL RESPONSE: %s:  %s" % ( len(response_text), response_text))
    return(response_text)


def twitter_reply(reply_type="", reply_text="", reply_handle=None, tweet_id=None):
    api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                      consumer_secret=TWITTER_SECRET,
                      access_token_key=TWITTER_ACCESS_TOKEN,
                      access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    if reply_type == "TWEET":
        print("TWEET ID I'M RESPONDING TO")
        print(tweet_id)
        response = api.PostUpdate(reply_text + " " + reply_handle, in_reply_to_status_id=tweet_id)
        #response = api.PostUpdate(reply_text, in_reply_to_status_id=tweet_id)
        print("twitter response")
        print(response)
    if reply_type == "DM":
        print("DM HANDLE I'M RESPONDING TO")
        print(reply_handle)
        response = api.PostDirectMessage(screen_name=reply_handle, text=reply_text)
        print("twitter response")
        print(response)
    pass

def responder(event, context):
    try:
        message = json.loads(event['Records'][0]['Sns']['Message'])
        content = message['content']
        #print_with_timestamp('Message became ', json.dumps(message))
        #print_with_timestamp('Content became ', json.dumps(content))
    except:
        message = event['Records'][0]['Sns']['Message']
        # print_with_timestamp('Message became ', message)
        # print_with_timestamp('Content became ', content)
    # make an email.parser out of the content of the message ( hopefully it's
    # multipart )
    #print_with_timestamp('CONTEXT ', dir(context))
    try:
        parsed_message = email.message_from_string(content)
        #xx print(parsed_message['to'])
        #xx print(parsed_message['from'])
    except:
        print_with_timestamp(
            "Failed to parse the content of the message: %s" % (content))
        return False

    email_content_decoded = None
    if parsed_message.is_multipart():
        for part in parsed_message.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            if ctype == 'text/html':
                #print("YES FOUND HTML")
                email_content_decoded = part.get_payload(decode=True)
    else:
        print_with_timestamp("message was not multipart")

    bsp = ParseHtml(email_content_decoded)
    
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
    # For now, remove the ' @handle ' from the input, if it's there
    search_text = re.sub("\s+@\S+", "", bsp.give_text())
    #respond_handles = " ".join(re.findall("@\S+", search_text)) 
    respond_handle = bsp.find_sender_handle()
    print("RESPOND HANDLES ARE")
    print(respond_handle)
    print("INPUT TWEET WAS ")
    print(search_text)
    try:
        #es = elasticsearch.Elasticsearch([ES_HOST])
        #results = es_search(es, searchword=search_text)
        awsauth = AWS4Auth(os.environ.get('FU_AWS_ACCESS_KEY_ID'),
                           os.environ.get('FU_AWS_SECRET_ACCESS_KEY'),
                           'us-west-2',
                           'es')
        es = elasticsearch.Elasticsearch(
                 hosts=[ES_HOST], 
                 connection_class=elasticsearch.RequestsHttpConnection, 
                 http_auth=awsauth,
                 use_ssl=True,
                 verify_certs=True)
        #print("ES INFO ES INFO ES INFO")
        #print(es.info())
        results = es_search(es, searchword=search_text)
    except Exception as e:
        print("JUMP THROUGH HOOPS TO TALK TO AMAZON ES, because %s" %(e))
        awsauth = AWS4Auth(os.environ.get('FU_AWS_ACCESS_KEY_ID'),
                           os.environ.get('FU_AWS_SECRET_ACCESS_KEY'),
                           'us-west-2',
                           'es')
        es = elasticsearch.Elasticsearch(host=ES_HOST, connection_class=RequestsHttpConnection, http_auth=awsauth)
        results = es_search(es, searchword=search_text)
    #pprint(results)
    if results['hits']['total'] <= 5:
       results = es_search(es, searchword='*')

    try:
        # 139 to account for the space before the at in the handle
        markov = markov_response(es_results=results, max_len=(139 - (len(respond_handle))))
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
        pass
   
