# All Snekbooru constants

GELBOORU_POSTS = "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1"
GELBOORU_TAGS  = "https://gelbooru.com/index.php?page=dapi&s=tag&q=index&json=1"
DANBOORU_POSTS = "https://danbooru.donmai.us/posts.json"
DANBOORU_TAGS  = "https://danbooru.donmai.us/tags.json"
DANBOORU_RANDOM= "https://danbooru.donmai.us/posts/random.json"
DANBOORU_COUNTS_POSTS = "https://danbooru.donmai.us/counts/posts.json"
KONACHAN_POSTS = "https://konachan.com/post.json"
KONACHAN_TAGS = "https://konachan.com/tag.json"
YANDERE_POSTS = "https://yande.re/post.json"
YANDERE_TAGS = "https://yande.re/tag.json"
RULE34_POSTS = "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index"
RULE34_TAGS  = "https://api.rule34.xxx/autocomplete.php"
HYPNOHUB_POSTS = "https://hypnohub.net/index.php?page=dapi&s=post&q=index&json=1"
HYPNOHUB_TAGS  = "https://hypnohub.net/index.php?page=dapi&s=tag&q=index&json=1"
ZEROCHAN_API = "https://www.zerochan.net"
E621_POSTS = "https://e621.net/posts.json"
E621_TAGS = "https://e621.net/tags.json"
E926_POSTS = "https://e926.net/posts.json"
E926_TAGS = "https://e926.net/tags.json"
XBOORU_POSTS = "https://xbooru.com/index.php?page=dapi&s=post&q=index&json=1"
XBOORU_TAGS  = "https://xbooru.com/index.php?page=dapi&s=tag&q=index&json=1"
SAFEBOORU_POSTS = "https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1"
SAFEBOORU_TAGS  = "https://safebooru.org/index.php?page=dapi&s=tag&q=index&json=1"
SZURUBOORU_POSTS = "https://szuru.libre.moe/api/posts"
SZURUBOORU_TAGS  = "https://szuru.libre.moe/api/tags"
HYBOORU_POSTS = "https://booru.funmaker.moe/api/post"
HYBOORU_TAGS  = "https://booru.funmaker.moe/api/tags"

USER_AGENT = "Snekbooru/6.0.2 Windows Dev Release (https://www.snekbooru.org)"
EHENTAI_API = "https://api.e-hentai.org/api.php"
DEFAULT_AI_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

BORING_TAGS = {
    "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls",
    "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys",
    "solo", "duo", "trio", "group",
    "absurdres", "highres", "lowres", "translation_request",
    "comic", "commentary", "tagme", "artist_request",
    "long_hair", "short_hair", "breasts", "large_breasts", "medium_breasts", "small_breasts",
    "looking_at_viewer", "smile", "open_mouth"
}

DEFAULT_HOTKEYS = {
    "focus_search": "Ctrl+L",
    "next_page": "Right",
    "prev_page": "Left",
    "random_post": "Ctrl+R",
    "open_full_media": "Return",
    "download_selected": "Ctrl+S",
    "favorite_selected": "Ctrl+B",
    "select_all_visible": "Ctrl+A",
    "deselect_all": "Esc",
    "go_to_home": "Ctrl+1",
    "go_to_browser": "Ctrl+2",
    "go_to_favorites": "Ctrl+3",
    "go_to_ai": "Ctrl+4",
}
