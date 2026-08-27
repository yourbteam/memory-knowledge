MIN_CHARS = 400


def split(text, min_chars=MIN_CHARS):
    out, buf = [], []
    for page_text in pages(text):
        for block in re.split(r"\n\s*\n", page_text):
            buf.append(block)
            if sum(len(b) for b in buf) >= min_chars:
                out.append("\n\n".join(buf))
                buf = []
        buf.append(FF)
    if buf:
        out.append("\n\n".join(buf))
    return out
