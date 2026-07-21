"""Layout parsers — exactly two cover the whole corpus (architecture validated).

    project_read.py -> running header + concept carry-forward (11 books, 0 body delimiters)
    band_book.py    -> 'Name of Activity:' body delimiter (A1/A2/A3 band books)

registry.detect_parser(doc) picks one by boundary signal before any chunking.
"""
