"""Layout parsers — exactly two cover the Band A and Band B corpus (architecture validated).

    project_read.py -> running header + concept carry-forward (11 books, 0 body delimiters)
    band_book.py    -> 'Name of Activity:' body delimiter (A1/A2/A3, B1/B2/B3 band books)
    band_c.py       -> stub: Band C's layout is not analysed yet, so it emits no chunks

registry.detect_parser(doc, band) picks one by boundary signal before any chunking; the band
letter comes from the source folder and is passed on to parse().
"""
