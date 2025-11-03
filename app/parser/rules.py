import re


# very common mainland China mobile pattern
PHONE_REGEX = re.compile(r'(1[3-9]\d{9})')

# common mainland postal code == 6 digits
POSTAL_REGEX = re.compile(r'(\d{6})')

# simple cleanup for separators
SEPARATORS = [',', '，', ';', '；', '。', '|', '/', '\n', '\r', '\t']


def clean_text(text: str) -> str:
    t = text
    for sep in SEPARATORS:
        t = t.replace(sep, ' ')
    # collapse excessive whitespace
    t = re.sub(r'\s+', ' ', t)
    return t.strip()
