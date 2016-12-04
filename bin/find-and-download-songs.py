#!/usr/bin/env python
#
# download the song list from bobdylan.com,
# then download the songs
# and then save them into a pymarkovchain database
#
import requests
import sys
import os
import hashlib
import Algorithmia
from elasticsearch import Elasticsearch
from time import sleep
from bs4 import BeautifulSoup as bs
from pprint import pprint

ES_HOST = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
ALG_KEY = os.environ.get('ALGORITHMIA_KEY', None)

es = Elasticsearch([ES_HOST])


if __name__ == "__main__":
    if ALG_KEY is None:
        raise Exception('no ALG_KEY environment var', 'None')
    #result = requests.get("http://www.bobdylan.com/songs/")
    client = Algorithmia.client('sim+G3wMj3e3IwYxbXBOK1/fblb1')
    algo = client.algo('nlp/AutoTag/1.0.0')
    song_list = requests.get("http://www.bobdylan.com/songs")
    song_list.raise_for_status()
    soup = bs(song_list.content, "html.parser")
    songs = soup.find_all(class_="song")
    for song in songs[200:1]:
        a = song.find('a')
        if a:
            print(a.get('href'), a.text)
            song_res = requests.get(a.get('href'))
            song_res.raise_for_status()
            song_soup = bs(song_res.content, "html.parser")
            lyrics = song_soup.find(class_="article-content lyrics")
            # lyrics.text.replace(copytext.text,"")
            copytext = song_soup.find(class_="copytext")
            if copytext is None:
                lyrictext = lyrics.text
            else:
                lyrictext = lyrics.text.replace(copytext.text, "")
            song_title = song_soup.find(class_="headline")
            credit = song_soup.find(class_="credit")
            if credit is None:
                credittext = ""
            else:
                credittext = credit.text
            #info = song_soup.find(class_="information")
            captioninfo = song_soup.find('div', {'class': 'caption'})
            if captioninfo is None:
                album = ""
            else:
                try:
                    album = captioninfo.find('small').text
                except AttributeError:
                    album = ""
            # print(lyrics.text)
            algo_res = algo.pipe(res['_source']['text'].encode('utf-8'))
            tags = also_res.results
            es_res = es.index(index='songs',
                              doc_type='bobdylan',
                              id=hashlib.md5(a.get('href')).hexdigest(),
                              body={'text': lyrictext.strip(),
                                    'title': song_title.text.strip(),
                                    'credit': credittext.strip(),
                                    'album': album.strip(),
                                    'url': a.get('href'),
                                    'tags': tags}
                              )
            sleep(3)
