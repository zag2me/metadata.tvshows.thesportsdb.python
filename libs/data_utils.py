# -*- coding: UTF-8 -*-
#

"""Functions to process data"""

from __future__ import absolute_import, unicode_literals

import re
from xbmc import Actor
from collections import namedtuple
from .utils import safe_get, logger
from . import settings, api_utils, cache

try:
    from typing import Optional, Text, Dict, List, Any  # pylint: disable=unused-import
    from xbmcgui import ListItem  # pylint: disable=unused-import
    InfoType = Dict[Text, Any]  # pylint: disable=invalid-name
except ImportError:
    pass

api_utils.set_headers(dict(settings.HEADERS))

TAG_RE = re.compile(r'<[^>]+>')

# Regular expressions are listed in order of priority.
SHOW_ID_REGEXPS = (r'(thesportsdb)\.com/league/(\d+)')

SUPPORTED_ARTWORK_TYPES = {'poster', 'banner'}
IMAGE_SIZES = ('large', 'original', 'medium')
CLEAN_PLOT_REPLACEMENTS = (
    ('<b>', '[B]'),
    ('</b>', '[/B]'),
    ('<i>', '[I]'),
    ('</i>', '[/I]'),
    ('</p><p>', '[CR]'),
)
VALIDEXTIDS = ['tmdb_id', 'imdb_id', 'tvdb_id']

UrlParseResult = namedtuple(
    'UrlParseResult', ['provider', 'show_id'])


def _clean_plot(plot):
    # type: (Text) -> Text
    """Replace HTML tags with Kodi skin tags"""
    for repl in CLEAN_PLOT_REPLACEMENTS:
        plot = plot.replace(repl[0], repl[1])
    plot = TAG_RE.sub('', plot)
    return plot


def _set_cast(cast_info, vtag):
    # type: (InfoType, ListItem) -> ListItem
    """Save cast info to list item"""
    cast = []
    for item in cast_info:
        actor = {
            'name': item['name'],
            'role': item.get('character', item.get('character_name', '')),
            'order': item['order'],
        }
        thumb = None
        if safe_get(item, 'profile_path') is not None:
            thumb = settings.IMAGEROOTURL + item['profile_path']
        cast.append(Actor(actor['name'], actor['role'], actor['order'], thumb))
    vtag.setCast(cast)


def _get_credits(show_info):
    # type: (InfoType) -> List[Text]
    """Extract show creator(s) and writer(s) from show info"""
    credits = []
    for item in show_info.get('created_by', []):
        credits.append(item['name'])
    for item in show_info.get('credits', {}).get('crew', []):
        isWriter = item.get('job', '').lower() == 'writer' or item.get(
            'department', '').lower() == 'writing'
        if isWriter and item.get('name') not in credits:
            credits.append(item['name'])
    return credits


def _get_directors(episode_info):
    # type: (InfoType) -> List[Text]
    """Extract episode writer(s) from episode info"""
    directors_ = []
    for item in episode_info.get('credits', {}).get('crew', []):
        if item.get('job') == 'Director':
            directors_.append(item['name'])
    return directors_


def _set_unique_ids(ext_ids, vtag):
    """Extract unique ID in various online databases"""
    for key, value in ext_ids.items():
        if key in VALIDEXTIDS and value:
            if key == 'tmdb_id':
                isTMDB = True
            else:
                isTMDB = False
            vtag.setUniqueID(str(value), type=key[:4], isDefault=isTMDB)


def _set_rating(the_info, vtag, episode=False):
    """Set show/episode rating"""
    first = True
    for rating_type in settings.RATING_TYPES:
        logger.debug('adding rating type of %s' % rating_type)
        rating = float(the_info.get('ratings', {}).get(
            rating_type, {}).get('rating', '0'))
        votes = int(the_info.get('ratings', {}).get(
            rating_type, {}).get('votes', '0'))
        logger.debug("adding rating of %s and votes of %s" %
                     (str(rating), str(votes)))
        if rating > 0:
            vtag.setRating(rating, votes=votes,
                           type=rating_type, isDefault=first)
            first = False


def _add_season_info(show_info, vtag):
    """Add info for league seasons"""
    params = {'id': show_info.get('idLeague', 0)}
    resp = api_utils.load_info(
        settings.SEASON_URL, params=params, verboselog=settings.VERBOSELOG)
    if resp is None:
        return
    seasons = []
    for season in resp.get('seasons'):
        season_name = season.get('strSeason')
        if season_name:
            season_num = int(season_name[:4])
            logger.debug(
                'adding information for season %s to list item' % season_name)
            vtag.addSeason(season_num, season_name)
            seasons.append({'season_num': season_num,
                           'season_name': season_name})
    return seasons


def set_show_artwork(show_info, list_item):
    """Set available images for a show"""
    vtag = list_item.getVideoInfoTag()
    images = []
    images.append(('fanart', show_info.get('strFanart1')))
    images.append(('fanart', show_info.get('strFanart2')))
    images.append(('fanart', show_info.get('strFanart3')))
    images.append(('fanart', show_info.get('strFanart1')))
    images.append(('poster', show_info.get('strPoster')))
    images.append(('banner', show_info.get('strBanner')))
    fanart_list = []
    for image_type, image in images:
        if image_type == 'fanart':
            if image:
                fanart_list.append(image.replace('\/', '/'))
        elif image:
            theurl = image.replace('\/', '/')
            previewurl = theurl + '/preview'
            vtag.addAvailableArtwork(
                theurl, art_type=image_type, preview=previewurl)
    if fanart_list:
        list_item.setAvailableFanart(fanart_list)
    return list_item


def add_main_show_info(list_item, show_info, full_info=True):
    # type: (ListItem, InfoType, bool) -> ListItem
    """Add main show info to a list item"""
    vtag = list_item.getVideoInfoTag()
    showname = show_info.get('strLeague')
    plot = _clean_plot(show_info.get('strDescriptionEN', ''))
    vtag.setTitle(showname)
    vtag.setOriginalTitle(showname)
    vtag.setTvShowTitle(showname)
    vtag.setPlot(plot)
    vtag.setPlotOutline(plot)
    vtag.setMediaType('tvshow')
    vtag.setEpisodeGuide(str(show_info['idLeague']))
    vtag.setYear(int(show_info.get('intFormedYear', '')[:4]))
    vtag.setPremiered(show_info.get('dateFirstEvent', ''))
    if full_info:
        vtag.setUniqueID(show_info.get('idLeague'),
                         type='tsdb', isDefault=True)
        vtag.setGenres([show_info.get('strSport', '')])
        vtag.setStudios([show_info.get('strTvRights', '')])
        vtag.setCountries([show_info.get('strCountry', '')])
#        vtag.setWriters(_get_credits(show_info))
        list_item = set_show_artwork(show_info, list_item)
        show_info['seasons'] = _add_season_info(show_info, vtag)
        cache.cache_show_info(show_info)
#        _set_cast(show_info['credits']['cast'], vtag)
#        _set_rating(show_info, vtag)
    else:
        image = show_info.get('strPoster')
        if image:
            theurl = image.replace('\/', '/')
            previewurl = theurl + '/preview'
            vtag.addAvailableArtwork(
                theurl, art_type='poster', preview=previewurl)
    logger.debug(
        'adding sports league information for %s to list item' % showname)
    return list_item


def add_episode_info(list_item, episode_info, full_info=True):
    # type: (ListItem, InfoType, bool) -> ListItem
    """Add episode info to a list item"""
    season = episode_info.get('strSeason', '0000')[:4]
    episode = episode_info.get('strEpisode', '0')
    title = episode_info.get('strEvent', 'Episode ' + episode)
    vtag = list_item.getVideoInfoTag()
    vtag.setSeason(int(season))
    vtag.setEpisode(int(episode))
    vtag.setMediaType('episode')
    air_date = episode_info.get('dateEvent')
    if air_date:
        vtag.setFirstAired(air_date)
        if not full_info:
            title = '%s.%s.%s' % (episode_info.get(
                'strLeague', ''), air_date.replace('-', ''), title)
    vtag.setTitle(title)
    if full_info:
        vtag.setTitle(title)
        raw_plot = episode_info.get('strDescriptionEN')
        if raw_plot:
            plot = _clean_plot(episode_info.get('strDescriptionEN', ''))
            vtag.setPlot(plot)
            vtag.setPlotOutline(plot)
        if air_date:
            vtag.setPremiered(air_date)
        rawurl = episode_info.get('strThumb', '')
        if rawurl:
            theurl = rawurl.replace('\/', '/')
            previewurl = theurl + '/preview'
            vtag.addAvailableArtwork(
                theurl, art_type='thumb', preview=previewurl)
        # _set_cast(episode_info['credits']['guest_stars'], vtag)
        # vtag.setWriters(_get_credits(episode_info))
        # vtag.setDirectors(_get_directors(episode_info))
    logger.debug('adding episode information for S%sE%s - %s to list item' %
                 (season, episode, title))
    return list_item


def parse_nfo_url(nfo):
    # type: (Text) -> Optional[UrlParseResult]
    """Extract show ID from NFO file contents"""
    sid_match = None
    for regexp in SHOW_ID_REGEXPS:
        logger.debug('trying regex to match service from parsing nfo:')
        logger.debug(regexp)
        show_id_match = re.search(regexp, nfo, re.I)
        if show_id_match:
            logger.debug('match group 1: ' + show_id_match.group(1))
            logger.debug('match group 2: ' + show_id_match.group(2))
            if show_id_match.group(1) == "thesportsdb":
                sid_match = UrlParseResult(
                    show_id_match.group(1), show_id_match.group(2))
                break
    return sid_match


def parse_media_id(title):
    title = title.lower()
    if title.startswith('tt') and title[2:].isdigit():
        # IMDB ID works alone because it is clear
        return {'type': 'imdb_id', 'title': title}
    # IMDB ID with prefix to match
    elif title.startswith('imdb/tt') and title[7:].isdigit():
        # IMDB ID works alone because it is clear
        return {'type': 'imdb_id', 'title': title[5:]}
    elif title.startswith('tmdb/') and title[5:].isdigit():  # TVDB ID
        return {'type': 'tmdb_id', 'title': title[5:]}
    elif title.startswith('tvdb/') and title[5:].isdigit():  # TVDB ID
        return {'type': 'tvdb_id', 'title': title[5:]}
    return None


def _check_youtube(key):
    chk_link = "https://www.youtube.com/watch?v="+key
    check = api_utils.load_info(chk_link, resp_type='not_json')
    if not check or "Video unavailable" in check:       # video not available
        return False
    return True
