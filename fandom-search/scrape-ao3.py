import os
import re
import argparse
import sys
from time import sleep

import requests
from bs4 import BeautifulSoup

class InlineDisplay:
    def __init__(self):
        self.currlen = 0

    def display(self, s):
        print(s, end=' ')
        sys.stdout.flush()
        self.currlen += len(s) + 1

    def reset(self):
        print('', end='\r')
        print(' ' * self.currlen, end='\r')
        sys.stdout.flush()
        self.currlen = 0

_id = InlineDisplay()
display = _id.display
reset_display = _id.reset

def request_loop(url, timeout=1.0, sleep_base=1.0):
    # We try 20 times. But we double the delay each time,
    # so that we don't get really annoying. Eventually the
    # delay could be many days long, but well before that
    # happens, the server should be up and running again,
    # and the request will finally succeed.

    response = None
    for i in range(20):
        display('Sleeping for {} seconds;'.format(sleep_base))
        sleep(sleep_base)
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError:
            code = response.status_code
            if code >= 400 and code < 500:
                display('Unrecoverable error ({})'.format(code))
                return ''
            else:
                sleep_base *= 2
                display('Recoverable error ({});'.format(code))
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.RequestException):
            sleep_base *= 2
            display('Unknown error, trying again;')
    return response.text

if __name__ == "__main__":

    # command line interface
    parser = argparse.ArgumentParser(description='Parse Fanfiction')
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-s', '--search', action='store',
        help="search term to search for a tag to scrape")
    group.add_argument(
        '-t', '--tag', action='store', nargs=1, help="the tag to be scraped")
    group.add_argument(
        '-u', '--url', action='store', nargs=1,
        help="the full URL of first page to be scraped")
    parser.add_argument(
        '-o', '--outfile', action='store', nargs=1, default='scraped-html',
        help="target directory for scraped files")
    parser.add_argument(
        '-p', '--startpage', action='store', nargs=1, default=[1], type=int,
        help="page on which to begin downloading (to resume a previous job)")

    args = parser.parse_args()
    argv = vars(args)

    searchVal = argv['search']
    tagVal = argv['tag']
    headerVal = argv['url']
    targetVal = argv['outfile']

    tagList = ["initialize"]
    resultList = ["initialize"]

    # tag scraping option
    if searchVal:
        pp = 1
        safeSearch = searchVal.replace(' ', '+')
        # the alternative here is to scrape this page and use regex to filter the results:
        # http://archiveofourown.org/media/Movies/fandoms?
        # the canonical filter is used here because the "fandom" filter on the beta tag search is broken as of November 2017
        searchRef = "http://archiveofourown.org/tags/search?utf8=%E2%9C%93&query%5Bname%5D=" + safeSearch + "&query%5Btype%5D=&query%5Bcanonical%5D=true&page="
        print('\nTags:')

        while (len(tagList)) != 0:
            resPage1 = requests.get(searchRef + str(pp))
            resSoup1 = BeautifulSoup(resPage1.text, "lxml")
            tagList = resSoup1(attrs={'href': re.compile('^/tags/[^s]....[^?].*')})

            for x in tagList:
                print(x.string)

            pp += 1

    error_works = set(['11442951'])

    # fan work scraping options
    if headerVal or tagVal:
        end = args.startpage[0] #pagination
        os.chdir(targetVal) #target directory

        while (len(resultList)) != 0:
            with open('log.txt', 'a') as f:
                f.write('\n\nPAGE ' + str(end) + '\n')
            print('Page {} '.format(end))

            display('Loading table of contents;')
            if headerVal:
                header = headerVal[0]

            if tagVal:
                modHeaderVal = tagVal[0].replace(' ', '%20')
                header = "http://archiveofourown.org/tags/" + modHeaderVal + "/works?page="

            page_request_url = header + str(end)
            toc_page = request_loop(page_request_url)

            if not toc_page:
                err_msg = 'Error loading TOC; aborting.'
                with open('log.txt', 'a') as f:
                    f.write(err_msg + '\n')
                display(err_msg)
                reset_display()
                continue

            toc_page_soup = BeautifulSoup(toc_page, "lxml")
            resultList = toc_page_soup(attrs={'href': re.compile('^/works/[0-9]+[0-9]$')})

            with open("log.txt", "a") as f:
                f.write('Number of Works on Page ' + str(end) + ': ' + str((len(resultList))) + '\n')
                f.write('Page URL: {}\n'.format(page_request_url))
                f.write('Progress: \n')

            reset_display()
            for x in resultList:
                body = str(x).split('"')
                docID = str(body[1]).split('/')[2]
                filename = str(docID) + '.html'

                if os.path.exists(filename):
                    display('Work {} already exists -- skpping;'.format(docID))
                    reset_display()
                    with open('log.txt', 'a') as f:
                        msg = ('skipped existing document {} on '
                               'page {} ({} bytes)\n')
                        f.write(msg.format(docID, str(end),
                                           os.path.getsize(filename)))
                elif docID in error_works:
                    display('Work {} is known to cause errors '
                            '-- skipping;'.format(docID))
                    reset_display()
                    with open('log.txt', 'a') as f:
                        msg = ('skipped document {} on page {} '
                               'known to cause errors')
                        f.write(msg.format(docID, str(end)))

                else:
                    display('Loading work {};'.format(docID))
                    work_request_url = "http://archiveofourown.org/" + body[1] + "?view_adult=true&view_full_work=true"
                    work_page = request_loop(work_request_url)
                    with open(filename, 'w', encoding='utf-8') as html_out:
                        bytes_written = html_out.write(str(work_page))

                    with open("log.txt", "a") as f:
                        msg = 'reached document {} on page {}, saved {} bytes\n'
                        f.write(msg.format(docID, str(end), bytes_written))
                    reset_display()

            reset_display()
            end += 1
