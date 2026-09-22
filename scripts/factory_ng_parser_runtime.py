"""Producer-local parser acceleration; source and acceptance gates stay authoritative."""
import functools
import hashlib
import json
from pathlib import Path
import re
import sys

from factory_ng_producer_cache import digest


class PatternCache:
    """A bounded re facade using public compiled-pattern APIs, scoped to parser modules."""
    def __init__(self, size=8192):
        self.cached_compile = functools.lru_cache(maxsize=size)(re.compile)

    def __getattr__(self, name):
        return getattr(re, name)

    def compile(self, pattern, flags=0):
        # DEBUG has observable printing; do not suppress it on a cache hit.
        if flags & re.DEBUG:
            return re.compile(pattern, flags)
        return self.cached_compile(pattern, flags)

    def match(self, pattern, string, flags=0):
        return self.compile(pattern, flags).match(string)

    def fullmatch(self, pattern, string, flags=0):
        return self.compile(pattern, flags).fullmatch(string)

    def search(self, pattern, string, flags=0):
        return self.compile(pattern, flags).search(string)

    def sub(self, pattern, repl, string, count=0, flags=0):
        return self.compile(pattern, flags).sub(repl, string, count)

    def subn(self, pattern, repl, string, count=0, flags=0):
        return self.compile(pattern, flags).subn(repl, string, count)

    def split(self, pattern, string, maxsplit=0, flags=0):
        return self.compile(pattern, flags).split(string, maxsplit)

    def findall(self, pattern, string, flags=0):
        return self.compile(pattern, flags).findall(string)

    def finditer(self, pattern, string, flags=0):
        return self.compile(pattern, flags).finditer(string)

    def purge(self):
        self.cached_compile.cache_clear()
        re.purge()


def install_patterns(parser, source):
    """Do not replace the process-wide re module or rewrite canonical source."""
    root = (Path(source) / 'scripts/paragraph').resolve()
    facade = PatternCache()
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if isinstance(path, str) and Path(path).resolve().is_relative_to(root):
            if getattr(module, 're', None) is re or isinstance(getattr(module, 're', None), PatternCache):
                module.re = facade
    return facade


def file_digest(cache, path):
    stat = path.stat()
    stamp = '%s:%s:%s:%s' % (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    found, value = cache.get('parser-file-hash-v1', path, stamp)
    if not found:
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        cache.put('parser-file-hash-v1', path, stamp, value)
    return value


def parser_code_stamp(source, cache):
    root = Path(source)
    # Include support modules, not just reparse.py. Tests are not parser inputs.
    paths = sorted(p for p in (root / 'scripts/paragraph').rglob('*.py')
                   if not p.name.startswith('test_') and '__pycache__' not in p.parts)
    paths += [root / 'corpus/Keywords.json'] if (root / 'corpus/Keywords.json').exists() else []
    return digest([(str(p.relative_to(root)), file_digest(cache, p)) for p in paths])


def shard_projection(data):
    if not isinstance(data, dict):
        return {'review': [], 'vocabulary': digest(['invalid-shard', data])}
    review = [(name, card) for name, card in sorted(data.items())
              if isinstance(card, dict) and card.get('status') == 'review']
    # Preserve input order: the parser's case-normalization dictionary uses
    # last occurrence wins. Card text/status do not affect these lookup tables.
    vocabulary = [(card.get('type'), card.get('sub_types')) if isinstance(card, dict)
                  else ('invalid-record', card) for card in data.values()]
    return {'review': review, 'vocabulary': digest(vocabulary)}


def corpus_snapshot(source, cache):
    directory = Path(source) / 'backend/data/carddb'
    paths = list(directory.glob('*.json'))
    rows = {}
    for path in paths:
        rows[path] = cache.file('parser-corpus-shard-v1', path, shard_projection) or shard_projection(None)
    # Match the parser's glob ordering for vocabulary; discovery sorts shards.
    vocabulary_stamp = digest([(path.name, rows[path]['vocabulary']) for path in paths
                               if not path.name.startswith('_')])
    cards = [tuple(item) for path in sorted(paths) for item in rows[path]['review']]
    return cards, vocabulary_stamp


def prepare_parser(source, parser, cache):
    """Load exact parser-built lookup tables and return discovery's input fingerprint."""
    facade = install_patterns(parser, source)
    code_stamp = digest([parser_code_stamp(source, cache),
                         file_digest(cache, Path(__file__).resolve()), list(sys.version_info[:3])])
    cards, vocabulary_stamp = corpus_snapshot(source, cache)
    cache.checkpoint()
    # Only real parsers have these globals; fixtures/alternate parsers simply
    # keep their original behavior and conservatively use corpus input hashes.
    fields = ('_SUBTYPE_VOCAB', '_LAND_SUBTYPE_VOCAB', '_SUBTYPE_WORDS_CACHE')
    values = vars(parser)
    if all(field in values for field in fields):
        table_stamp = digest([code_stamp, vocabulary_stamp])
        key = str(Path(source).resolve())
        found, tables = cache.get('parser-vocabulary-v1', key, table_stamp)
        if not found:
            # Use the canonical functions, including their extra subtype rules.
            parser.subtype_vocab()
            parser.subtype_is_land('')
            parser._subtype_words()
            tables = [parser._SUBTYPE_VOCAB, sorted(parser._LAND_SUBTYPE_VOCAB),
                      sorted(parser._SUBTYPE_WORDS_CACHE)]
            cache.put('parser-vocabulary-v1', key, table_stamp, tables)
        else:
            parser._SUBTYPE_VOCAB = tables[0]
            parser._LAND_SUBTYPE_VOCAB = set(tables[1])
            parser._SUBTYPE_WORDS_CACHE = set(tables[2])
        vocabulary_stamp = digest(tables)
    registered = sorted(values.get('REGISTERED', []))
    stamp = digest(['parser-runtime-v1', code_stamp, registered, vocabulary_stamp])
    cache.checkpoint()
    return cards, stamp, facade
