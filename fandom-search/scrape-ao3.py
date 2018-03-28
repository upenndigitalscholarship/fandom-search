import os
import re
import argparse
import sys
import random
from time import sleep

import requests
from bs4 import BeautifulSoup

class Logger:
    def __init__(self, logfile='log.txt'):
        self.logfile = logfile

    def log(self, msg, newline=True):
        with open(self.logfile, 'a') as f:
            f.write(msg)
            if newline:
                f.write('\n')

_logger = Logger()
log = _logger.log

_error_id_log = Logger(logfile='error-ids.txt')
log_error_id = _error_id_log.log

def load_error_ids():
    with open(_error_id_log.logfile) as ip:
        ids = set(l.strip() for l in ip.readlines())
        return ids

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

def request_loop(url, timeout=4.0, sleep_base=1.0):
    # We try 20 times. But we double the delay each time,
    # so that we don't get really annoying. Eventually the
    # delay will be more than an hour long, at which point
    # we'll try a few more times, and then give up.

    orig_url = url
    for i in range(20):
        if sleep_base > 7200:  # Only delay up to an hour.
            sleep_base /= 2
            url = '{}#{}'.format(orig_url, random.randrange(1000))
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
        except requests.exceptions.ReadTimeout as exc:
            sleep_base *= 2
            display('Read timed out -- trying again;')
        except requests.exceptions.RequestException as exc:
            sleep_base *= 2
            display('Unexpected error ({}), trying again;\n'.format(exc))
    else:
        return None

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
        searchRef = "https://archiveofourown.org/tags/search?utf8=%E2%9C%93&query%5Bname%5D=" + safeSearch + "&query%5Btype%5D=&query%5Bcanonical%5D=true&page="
        print('\nTags:')

        while (len(tagList)) != 0:
            resPage1 = requests.get(searchRef + str(pp))
            resSoup1 = BeautifulSoup(resPage1.text, "lxml")
            tagList = resSoup1(attrs={'href': re.compile('^/tags/[^s]....[^?].*')})

            for x in tagList:
                print(x.string)

            pp += 1


    # fan work scraping options
    if headerVal or tagVal:
        end = args.startpage[0] #pagination
        os.chdir(targetVal) #target directory
        error_works = load_error_ids()

        while (len(resultList)) != 0:
            log('\n\nPAGE ' + str(end))
            print('Page {} '.format(end))

            display('Loading table of contents;')
            if headerVal:
                header = headerVal[0]

            if tagVal:
                modHeaderVal = tagVal[0].replace(' ', '%20')
                header = "https://archiveofourown.org/tags/" + modHeaderVal + "/works?page="

            page_request_url = header + str(end)
            toc_page = request_loop(page_request_url)

            if not toc_page:
                err_msg = 'Error loading TOC; aborting.'
                log(err_msg)
                display(err_msg)
                reset_display()
                continue

            toc_page_soup = BeautifulSoup(toc_page, "lxml")
            resultList = toc_page_soup(attrs={'href': re.compile('^/works/[0-9]+[0-9]$')})

            log('Number of Works on Page {}: {}'.format(end, len(resultList)))
            log('Page URL: {}'.format(page_request_url))
            log('Progress: ')

            reset_display()
            for x in resultList:
                body = str(x).split('"')
                docID = str(body[1]).split('/')[2]
                filename = str(docID) + '.html'

                if os.path.exists(filename):
                    display('Work {} already exists -- skpping;'.format(docID))
                    reset_display()
                    msg = ('skipped existing document {} on '
                           'page {} ({} bytes)')
                    log(msg.format(docID, str(end),
                                   os.path.getsize(filename)))
                elif docID in error_works:
                    display('Work {} is known to cause errors '
                            '-- skipping;'.format(docID))
                    reset_display()
                    msg = ('skipped document {} on page {} '
                           'known to cause errors')
                    log(msg.format(docID, str(end)))

                else:
                    display('Loading work {};'.format(docID))
                    work_request_url = "https://archiveofourown.org/" + body[1] + "?view_adult=true&view_full_work=true"
                    work_page = request_loop(work_request_url)

                    if work_page is None:
                        error_works.add(docID)
                        log_error_id(docID)
                        continue

                    with open(filename, 'w', encoding='utf-8') as html_out:
                        bytes_written = html_out.write(str(work_page))

                    msg = 'reached document {} on page {}, saved {} bytes'
                    log(msg.format(docID, str(end), bytes_written))
                    reset_display()

            reset_display()
            end += 1
