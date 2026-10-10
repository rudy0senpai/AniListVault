"""Public read-only MangaDex and Kitsu manga metadata adapters."""
from __future__ import annotations
import json, logging, urllib.parse, urllib.error, urllib.request
from animevault.media_types import MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA, category_from_origin
from animevault.services.providers.base import ProviderError, parse_retry_after
from animevault.services.providers.literature import LiteratureMetadata
logger = logging.getLogger(__name__)

def _get(url, *, provider, headers=None, timeout=12):
    req=urllib.request.Request(url,headers={"User-Agent":"AniListVault/0.3.1 (metadata lookup)","Accept":"application/json",**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp: return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code==429: raise ProviderError(f"{provider} rate limited (429)",status_code=429,retryable=True,retry_after=parse_retry_after(exc.headers.get("Retry-After"),60),provider=provider)
        raise ProviderError(f"{provider} HTTP {exc.code}",status_code=exc.code,retryable=exc.code>=500,provider=provider)
    except urllib.error.URLError as exc: raise ProviderError(f"{provider} network error: {exc}",retryable=True,provider=provider)
    except (ValueError,UnicodeDecodeError) as exc: raise ProviderError(f"{provider} malformed JSON response: {exc}",retryable=False,provider=provider)

def _md_text(value,lang="en",fallback=True):
    if not isinstance(value,dict): return ""
    exact=(value.get(lang) or "").strip()
    if exact or not fallback: return exact
    return next((str(text).strip() for text in value.values() if str(text or "").strip()),"")

def normalize_mangadex(item):
    attrs=item.get("attributes") or {}; titles=attrs.get("title") or {}; english=_md_text(titles,"en",False)
    native=_md_text(titles,"ja",False) or _md_text(titles,"ko",False) or _md_text(titles,"zh",False); title=english or _md_text(titles)
    synonyms=[v.strip() for pair in (attrs.get("altTitles") or []) if isinstance(pair,dict) for v in pair.values() if isinstance(v,str) and v.strip()]
    raw_origin=(attrs.get("originalLanguage") or "").upper()
    origin={"JA":"JP","KO":"KR","ZH":"CN"}.get(raw_origin,raw_origin)
    mid=str(item.get("id") or ""); cover=""; authors=[]; artists=[]
    for rel in item.get("relationships") or []:
        if rel.get("type")=="cover_art":
            filename=((rel.get("attributes") or {}).get("fileName") or "").strip()
            if filename and mid: cover=f"https://uploads.mangadex.org/covers/{mid}/{urllib.parse.quote(filename)}.512.jpg"
        elif rel.get("type") in {"author", "artist"}:
            name=((rel.get("attributes") or {}).get("name") or "").strip()
            if name: (authors if rel["type"]=="author" else artists).append(name)
    links=attrs.get("links") or {}
    try: mal_id=int(links.get("mal")) if links.get("mal") else None
    except (TypeError,ValueError): mal_id=None
    try: anilist_id=int(links.get("al")) if links.get("al") else None
    except (TypeError,ValueError): anilist_id=None
    genres=[t.get("attributes",{}).get("name",{}).get("en","") for t in attrs.get("tags") or []]
    return LiteratureMetadata(title=title,title_en=english,title_native=native,synonyms=list(dict.fromkeys(synonyms)),
        category=category_from_origin(origin) or MEDIA_MANGA,format="MANGA",status=(attrs.get("status") or "").upper(),pub_status=(attrs.get("status") or "").upper(),
        synopsis=_md_text(attrs.get("description") or {}),genres=[g for g in genres if g],authors=authors,artists=artists,
        chapters=int(attrs.get("lastChapter") or 0) if str(attrs.get("lastChapter") or "").isdigit() else 0,
        volumes=int(attrs.get("lastVolume") or 0) if str(attrs.get("lastVolume") or "").isdigit() else 0,
        started_at=str(attrs.get("year") or ""),origin_country=origin,cover_url=cover,anilist_id=anilist_id,mal_id=mal_id,
        source_provider="MangaDex",provider_ids={"mangadex":mid} if mid else {})

class MangaDexProvider:
    """Public MangaDex search, used as a conditional fallback."""
    name="mangadex"; base_url="https://api.mangadex.org"
    def is_available(self): return True
    def search(self,query,limit=10):
        params=[("title",query.strip()),("limit",str(min(limit,20))),("includes[]","cover_art"),("includes[]","author"),("includes[]","artist")]
        data=_get(f"{self.base_url}/manga?{urllib.parse.urlencode(params)}",provider=self.name)
        return [normalize_mangadex(x) for x in data.get("data",[])]
    def get_details(self,provider_id):
        params=urllib.parse.urlencode([("includes[]","cover_art"),("includes[]","author"),("includes[]","artist")]); data=_get(f"{self.base_url}/manga/{urllib.parse.quote(str(provider_id))}?{params}",provider=self.name)
        if not data.get("data"): raise ProviderError("MangaDex manga not found",status_code=404,retryable=False,provider=self.name)
        return normalize_mangadex(data["data"])

def normalize_kitsu_manga(item):
    attrs=item.get("attributes") or {}; titles=attrs.get("titles") or {}; english=(titles.get("en") or titles.get("en_us") or "").strip()
    native=(titles.get("ja_jp") or titles.get("ko_kr") or titles.get("zh_cn") or "").strip(); title=(attrs.get("canonicalTitle") or english or native).strip()
    posters=attrs.get("posterImage") or {}; kid=str(item.get("id") or "")
    return LiteratureMetadata(title=title,title_en=english,title_native=native,
        synonyms=list(dict.fromkeys(str(x).strip() for x in (attrs.get("abbreviatedTitles") or []) if str(x).strip())),category="",
        format=(attrs.get("subtype") or "MANGA").upper(),status=(attrs.get("status") or "").upper(),pub_status=(attrs.get("status") or "").upper(),
        synopsis=(attrs.get("synopsis") or "").strip(),chapters=int(attrs.get("chapterCount") or 0),volumes=int(attrs.get("volumeCount") or 0),
        started_at=(attrs.get("startDate") or "")[:10],ended_at=(attrs.get("endDate") or "")[:10],
        cover_url=posters.get("original") or posters.get("large") or posters.get("medium") or "",kitsu_id=kid or None,
        source_provider="Kitsu",provider_ids={"kitsu":kid} if kid else {})

class KitsuMangaProvider:
    """Kitsu public read-only manga search via its JSON:API resource."""
    name="kitsu-manga"; base_url="https://kitsu.app/api/edge"
    def is_available(self): return True
    def search(self,query,limit=10):
        params=[("filter[text]",query.strip()),("page[limit]",str(min(limit,20)))]
        data=_get(f"{self.base_url}/manga?{urllib.parse.urlencode(params)}",provider=self.name,headers={"Accept":"application/vnd.api+json"})
        return [normalize_kitsu_manga(x) for x in data.get("data",[])]
    def get_details(self,provider_id):
        data=_get(f"{self.base_url}/manga/{urllib.parse.quote(str(provider_id))}",provider=self.name,headers={"Accept":"application/vnd.api+json"})
        if not data.get("data"): raise ProviderError("Kitsu manga not found",status_code=404,retryable=False,provider=self.name)
        return normalize_kitsu_manga(data["data"])
