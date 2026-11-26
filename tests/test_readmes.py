"""README.md and README.es.md must say the same thing. The text is translated; the structure,
links, commands and tables must match, so the Spanish one can never silently fall behind."""

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
EN = (ROOT / "README.md").read_text(encoding="utf-8")
ES = (ROOT / "README.es.md").read_text(encoding="utf-8")
SWITCHER = {"README.md", "README.es.md"}
COMMANDS = ("uv", "unboring", "cd", "npx", "npm", "pip", "git")


def without_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def heading_levels(text: str) -> list[int]:
    return [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s", without_code(text), re.M)]


def link_targets(text: str) -> Counter:
    """Per-language assets (docs/images/review-en.gif, review-es.gif) count as the same link."""
    return Counter(
        re.sub(r"-(en|es)(\.\w+)$", r"-<lang>\2", t)
        for t in re.findall(r"\]\(([^)]+)\)", without_code(text))
        if t not in SWITCHER
    )


def code_blocks(text: str) -> list[tuple[str, list[str]]]:
    """(language, commands): for each command line, the command and its subcommand. Comments,
    example folder names and free-text arguments are translated, so they are ignored."""
    out = []
    for lang, body in re.findall(r"```(\w*)\n(.*?)```", text, flags=re.S):
        commands = []
        for line in body.splitlines():
            tokens = line.split("#")[0].split()
            if not tokens:
                continue
            if tokens[0] in COMMANDS:
                commands.append(" ".join(t for t in tokens[:3] if not t.startswith(("tu-", "your-"))))
            elif tokens[0].startswith("/"):
                commands.append(tokens[0])
        out.append((lang, commands if lang else []))  # untagged blocks are diagrams: only their place counts
    return out


def table_rows(text: str) -> int:
    return sum(1 for line in without_code(text).splitlines() if line.startswith("|"))


def test_both_link_to_each_other_at_the_top():
    """The language switcher, with or without flags, and the same in both."""
    en_top, es_top = "\n".join(EN.splitlines()[:5]), "\n".join(ES.splitlines()[:5])
    assert re.search(r"\[(🇪🇸 )?Español\]\(README\.es\.md\)", en_top)
    assert re.search(r"\[(🇬🇧 )?English\]\(README\.md\)", es_top)
    assert ("🇬🇧" in en_top) == ("🇬🇧" in es_top), "add the flags to both language switchers"


def test_same_sections():
    assert heading_levels(EN) == heading_levels(ES), "README.es.md has different sections: update both READMEs together"


def test_same_links():
    assert link_targets(EN) == link_targets(ES), "a link was added or removed in only one README"


def test_same_commands():
    assert code_blocks(EN) == code_blocks(ES), "a code block or command differs between the READMEs"


def test_same_tables():
    assert table_rows(EN) == table_rows(ES), "a table row was added or removed in only one README"
