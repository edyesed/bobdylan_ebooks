#!/usr/bin/env python
#
# If you want to run locally, you can run this
#
import elasticsearch
import os
import sys
import pymarkovchain
from pprint import pprint

ES_HOST = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')

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
         return es_search(es=es, searchword=searchword, min_hits=300, search_type="not_match", fuck_it_well_do_it_live=True)

if __name__ == "__main__":
    es = elasticsearch.Elasticsearch([ES_HOST])
    searchword = sys.argv[1]

    try:
        ###
        results = es_search(es=es, searchword=searchword)
        #results = es_search(es=es, searchword=searchword, search_type="not_match")
        # ok 
        mc = pymarkovchain.MarkovChain()
        for songwords in results['hits']['hits']:
            #print("training with text: %s" % (songwords['_source']['text']))
            mc.generateDatabase(songwords['_source']['text'], sentenceSep='\r\n')
        # concat four markovs together
        response_text = mc.generateString()
        response_text += " " + mc.generateString()
        response_text += " " + mc.generateString()
        response_text += " " + mc.generateString()
        #response_text = mc.generateStringWithSeed(searchword)
        print("Response would be:\n%s\n" % (response_text))
        max_tweet_len = 280
        keepwords = ""
        if len(response_text) > max_tweet_len:
           words = response_text.split()
           for word in words:
              #print("KEEPWORDS: %s " % (keepwords))
              if len(keepwords) > 280:
                  raise Exception("Too long of a response")
              if len(keepwords) + len(word) > 280:
                  # RETURN NOW THIS IS ENOUGH
                  break
              keepwords = keepwords + " " + word
        else:
           keepwords = response_text
        print("ACTUAL RESPONSE: %s" % ( len(keepwords)))
        try:
            print(keepwords.lowercase())
        except:
            print(keepwords)

    except Exception as e:
        print("Failed as exception %s" % (e))

