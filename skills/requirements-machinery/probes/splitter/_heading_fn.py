HEADING = re.compile(r"^\s{0,4}(\d+(?:\.\d+)*)\.?\s+\S.{0,80}$")


def split(text):
    out, buf = [], []
    for page_text in pages(text):
        for line in page_text.split("\n"):
            if HEADING.match(line) and buf and any(l.strip() for l in buf):
                out.append("\n".join(buf))
                buf = []
            buf.append(line)
        buf.append(FF)
    if buf:
        out.append("\n".join(buf))
    return out
