"""Unit tests for sources.py helpers. No network: every input is a small
fake string or dict copied from a real case we found in the data."""
import pytest

from JobScouterMCP.sources import html_to_text, lever_description, parse_job_id


# html_to_text ---------------------------------------------------------------

def test_greenhouse_double_escaped_html():
    raw = ("&lt;h2&gt;About the role&lt;/h2&gt;"
           "&lt;p&gt;You will build &lt;strong&gt;ML&lt;/strong&gt; systems.&amp;nbsp;Remote-friendly.&lt;/p&gt;"
           "&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;R&amp;amp;D experience&lt;/li&gt;"
           "&lt;li&gt;Less than &amp;lt;5 years is fine&lt;/li&gt;&lt;/ul&gt;")
    assert html_to_text(raw) == (
        "About the role\n"
        "You will build ML systems. Remote-friendly.\n"
        "- Python\n"
        "- R&D experience\n"
        "- Less than <5 years is fine"
    )


def test_lever_newline_before_each_li():
    raw = "<div>\n\n<li>Python</li>\n<li>SQL</li>\n</div>"
    assert html_to_text(raw) == "- Python\n- SQL"


def test_lever_paragraph_inside_li():
    raw = "<li>\n<p><strong>Build.</strong> New role.</p>\n</li>\n<li>\n<p>Ownership.</p>\n</li>"
    assert html_to_text(raw) == "- Build. New role.\n- Ownership."


def test_ashby_styled_paragraphs():
    raw = ('<p style="min-height:1.5em">Intro.</p><p style="min-height:1.5em"></p>'
           '<ul style="min-height:1.5em"><li><p style="min-height:1.5em">Contracts</p></li>'
           '<li><p style="min-height:1.5em">Clients</p></li></ul><p>Closing.</p>')
    assert html_to_text(raw) == "Intro.\n- Contracts\n- Clients\n\nClosing."


def test_missing_description_is_empty_text():
    assert html_to_text(None) == ""


# parse_job_id ---------------------------------------------------------------

def test_parse_job_id():
    assert parse_job_id("greenhouse:Anthropic:5436293008") == ("greenhouse", "Anthropic", "5436293008")


def test_parse_job_id_keeps_colons_in_the_last_piece():
    assert parse_job_id("ashby:OpenAI:a:b") == ("ashby", "OpenAI", "a:b")


@pytest.mark.parametrize("bad_id", ["5436293008", "greenhouse::123", "", "lever:Aleph"])
def test_parse_job_id_rejects_bad_ids(bad_id):
    with pytest.raises(ValueError):
        parse_job_id(bad_id)


# lever_description ----------------------------------------------------------

def test_lever_description_joins_intro_lists_and_closing():
    job = {
        "description": "<div>Intro about <strong>Aleph</strong>.</div>",
        "lists": [{"text": "Requirements:", "content": "\n<li>Python</li>\n<li>SQL</li>\n"}],
        "additional": "",
    }
    assert lever_description(job) == "Intro about Aleph.\n\nRequirements:\n- Python\n- SQL"