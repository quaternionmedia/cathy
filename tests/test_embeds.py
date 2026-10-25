import pytest

from cathy import embeds


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ?wmode=opaque",
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
    ],
)
def test_a_video_url_yields_its_id(url):
    assert embeds.youtube_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/embed/videoseries?list=PL0123456789",
        "https://www.youtube.com/playlist?list=PL0123456789",
        "https://www.youtube.com/user/abcdefghijk",
        "https://example.com/youtube.com/watch?v=dQw4w9WgXcQ",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_a_playlist_a_channel_or_another_host_yields_no_id(url):
    assert embeds.youtube_id(url) is None


def test_vimeo_ids():
    assert embeds.vimeo_id("https://player.vimeo.com/video/123456789?h=abc") == "123456789"
    assert embeds.vimeo_id("https://vimeo.com/123456789") == "123456789"
    assert embeds.vimeo_id("https://vimeo.com/channels/staffpicks") is None


def test_a_video_becomes_a_player():
    assert embeds.player('<iframe src="//www.youtube.com/embed/dQw4w9WgXcQ"></iframe>') == (
        '<div class="video"><iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"'
        ' frameborder="0" allowfullscreen></iframe></div>'
    )


def test_an_embedly_wrapper_is_unwrapped_to_the_media_it_carries():
    iframe = (
        '<iframe src="//cdn.embedly.com/widgets/media.html?src=x&amp;'
        'url=https%3A%2F%2Fsoundcloud.com%2Fa%2Fb" title=""></iframe>'
    )
    assert embeds.player(iframe) == "[Listen on SoundCloud](https://soundcloud.com/a/b)"


def test_a_playlist_becomes_a_link_that_keeps_its_url():
    iframe = '<iframe src="https://www.youtube.com/embed/videoseries?list=PL0123456789" title="YouTube embed"></iframe>'
    assert embeds.player(iframe) == "[Watch on YouTube](https://www.youtube.com/embed/videoseries?list=PL0123456789)"


def test_a_link_survives_parentheses_and_brackets():
    iframe = "<iframe src='https://example.com/a (b).html' title='[live] set'></iframe>"
    assert embeds.player(iframe) == "[\\[live\\] set](https://example.com/a%20%28b%29.html)"


def test_an_iframe_without_a_source_leaves_nothing():
    assert embeds.player("<iframe></iframe>") == ""
