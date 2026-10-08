"""Original weighted-break fixtures, flat pattern oracle and agent contracts."""
import copy
from contextlib import closing
import hashlib
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest
import test_editing_cli as editing
from test_mcp import Client


def pattern(text, weights, **kw):
    return dict(text=text, weights=weights, **kw)


def oracle(rules, word):
    """Flat enumeration of all pattern occurrences; independent of the trie."""
    token = word.lower() if rules.get('case') == 'ascii_lower' else word
    weights = [0] * (len(token) + 1)
    for p in rules.get('patterns', []):
        at = token.find(p['text'])
        while at != -1:
            if (not p.get('at_start') or at == 0) and (not p.get('at_end') or at + len(p['text']) == len(token)):
                for i, v in enumerate(p['weights']):
                    weights[at+i] = max(weights[at+i], v)
            at = token.find(p['text'], at + 1)
    candidates = [i for i in range(1, len(token)) if weights[i] % 2]
    if token in rules.get('exceptions', {}):
        candidates = rules['exceptions'][token]
        weights = None
    # This oracle is used only on ASCII fixtures; Unicode cases have hand-derived expectations.
    points = [i for i in candidates if i >= rules.get('min_left', 2) and len(token)-i >= rules.get('min_right', 2)]
    edges = [0] + points + [len(word)]
    return weights, candidates, points, [word[a:b] for a, b in zip(edges, edges[1:])]


class HyphenationTests(unittest.TestCase):
    def invoke(self, request, code=None):
        result = editing.EditingCliTests.invoke(self, request, expected=1 if code else 0)
        if code:
            self.assertEqual(result['code'], code)
        return result

    def inspect(self, rules, words, **kw):
        return self.invoke(dict(command='text.hyphenate', rules=rules, words=words, **kw))

    def test_competing_priorities_and_strict_maximum_not_last_wins(self):
        rules = dict(min_left=1, min_right=1, patterns=[pattern('abcd', [0, 1, 3, 5, 0]), pattern('bc', [2, 4, 6])])
        for ps in [rules['patterns'], list(reversed(rules['patterns'])), rules['patterns']*2]:
            result = self.inspect(dict(rules, patterns=ps), ['abcd'])['words'][0]
            self.assertEqual(result['weights'], [0, 2, 4, 6, 0])
            self.assertEqual(result['breaks'], [])
        rules['patterns'].append(pattern('c', [7, 0]))
        result = self.inspect(rules, ['abcd'])['words'][0]
        self.assertEqual(result['breaks'], [2]); self.assertEqual(result['parts'], ['ab', 'cd'])

    def test_all_anchor_combinations_and_overlapping_occurrences(self):
        words = ['ab', 'abab', 'zab', 'abz', 'zabz', 'aaaaa']
        for start, end in itertools.product([False, True], repeat=2):
            rules = dict(min_left=1, min_right=1, patterns=[pattern('ab', [1, 3, 5], at_start=start, at_end=end), pattern('aa', [0, 1, 0])])
            for actual, word in zip(self.inspect(rules, words)['words'], words):
                weights, candidates, points, parts = oracle(rules, word)
                self.assertEqual((actual['weights'], actual['candidates'], actual['breaks'], actual['parts']), (weights, candidates, points, parts))

    def test_exhaustive_binary_tokens_against_flat_reference(self):
        rng = random.Random(651)
        patterns = []
        for n in range(1, 5):
            for letters in itertools.product('ab', repeat=n):
                patterns.append(pattern(''.join(letters), [rng.randrange(10) for _ in range(n+1)], at_start=rng.choice([False, True]), at_end=rng.choice([False, True])))
        words = [''.join(v) for n in range(1, 8) for v in itertools.product('ab', repeat=n)]
        for left, right in [(1, 1), (2, 3), (4, 2)]:
            rules = dict(patterns=patterns, min_left=left, min_right=right, exceptions={'abba': [1, 3], 'aa': []})
            for actual, word in zip(self.inspect(rules, words)['words'], words):
                self.assertEqual((actual['weights'], actual['candidates'], actual['breaks'], actual['parts']), oracle(rules, word))

    def test_exceptions_replace_patterns_and_still_obey_minima(self):
        rules = dict(patterns=[pattern('a', [1, 1])], exceptions={'aaaaaa': [1, 3, 5], 'aaaa': []})
        results = self.inspect(rules, ['aaaaaa', 'aaaa', 'aaaaa'])['words']
        self.assertEqual(results[0]['candidates'], [1, 3, 5]); self.assertEqual(results[0]['breaks'], [3])
        self.assertIsNone(results[0]['weights']); self.assertEqual(results[0]['source'], 'exception')
        self.assertEqual(results[1]['breaks'], []); self.assertEqual(results[2]['breaks'], [2, 3])

    def test_graphemes_scalar_offsets_combining_marks_emoji_and_joiners(self):
        words = ['a\u0301bc\u0327d', 'a\U0001f469\u200d\U0001f4bbb', '\U0001f1ec\U0001f1e7ab']
        boundaries = [[0, 2, 3, 5, 6], [0, 1, 4, 5], [0, 2, 3, 4]]
        rules = dict(min_left=1, min_right=1, patterns=[pattern(c, [1, 1]) for c in sorted(set(''.join(words)))])
        for result, expected in zip(self.inspect(rules, words)['words'], boundaries):
            self.assertEqual(result['grapheme_boundaries'], expected)
            self.assertEqual(result['breaks'], expected[1:-1]); self.assertEqual(''.join(result['parts']), result['word'])
        rules.update(min_left=2, min_right=2)
        results = self.inspect(rules, words)['words']
        self.assertEqual([r['breaks'] for r in results], [[3], [], []])

    def test_exact_unicode_and_explicit_ascii_case_without_source_changes(self):
        rules = dict(case='ascii_lower', min_left=1, min_right=1, patterns=[pattern('ab', [0, 1, 0]), pattern('\u00e9c', [0, 1, 0])])
        words = ['AB', '\u00e9c', '\u00c9C', 'e\u0301c']
        before = copy.deepcopy((rules, words)); results = self.inspect(rules, words)['words']
        self.assertEqual([r['breaks'] for r in results], [[1], [1], [], []])
        self.assertEqual([r['word'] for r in results], words); self.assertEqual((rules, words), before)
        self.assertEqual(results[0]['parts'], ['A', 'B'])
        self.assertEqual(self.inspect(dict(rules, case='exact'), ['AB'])['words'][0]['breaks'], [])

    def test_hash_normalizes_defaults_and_map_order_but_retains_declared_rules(self):
        rules = dict(patterns=[pattern('ab', [0, 1, 0])], exceptions={'abc': [1], 'bc': []})
        normalized = dict(case='exact', min_left=2, min_right=2, patterns=[pattern('ab', [0, 1, 0], at_start=False, at_end=False)], exceptions={'abc': [1], 'bc': []})
        digest = hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(self.inspect(rules, [])['rules_sha256'], digest)
        self.assertEqual(self.inspect(normalized, ['abcd'])['rules_sha256'], digest)
        normalized['exceptions'] = {'bc': [], 'abc': [1]}
        self.assertEqual(self.inspect(normalized, [])['rules_sha256'], digest)
        normalized['min_left'] = 1
        self.assertNotEqual(self.inspect(normalized, [])['rules_sha256'], digest)

    def test_punctuation_digits_and_literal_period_have_no_parser_magic(self):
        rules = dict(min_left=1, min_right=1, patterns=[pattern('1.a/', [0, 1, 1, 1, 0], at_start=True, at_end=True)])
        result = self.inspect(rules, ['1.a/', 'x1.a/'])['words']
        self.assertEqual(result[0]['breaks'], [1, 2, 3]); self.assertEqual(result[1]['breaks'], [])

    def test_invalid_patterns_exceptions_and_unknown_semantics_fail_explicitly(self):
        invalid = [dict(patterns=[pattern('', [0])]), dict(patterns=[pattern('ab', [1, 2])]), dict(patterns=[pattern('ab', [0, 10, 0])]), dict(patterns=[pattern('a b', [0]*4)]), dict(case='ascii_lower', patterns=[pattern('AB', [0, 1, 0])]), dict(exceptions={'abcd': [2, 1]}), dict(exceptions={'abcd': [2, 2]}), dict(exceptions={'abcd': [0]}), dict(exceptions={'abcd': [4]}), dict(exceptions={'a\u0301bc': [1]}), dict(case='ascii_lower', exceptions={'Abcd': [2]}), dict(min_left=0), dict(min_right=129)]
        for rules in invalid:
            with self.subTest(rules=rules):
                self.invoke(dict(command='text.hyphenate', rules=rules, words=[]), 'INVALID_HYPHENATION')
        for rules in [dict(language='en'), dict(patterns=[dict(text='ab', weights=[0, 1, 0], replacement='x')]), dict(case='unicode_fold')]:
            self.invoke(dict(command='text.hyphenate', rules=rules, words=[]), 'INVALID_REQUEST')

    def test_invalid_input_batch_is_atomic_and_rejects_format_controls(self):
        for word in ['', 'a b', 'a\nb', 'a\tb', 'a\u00adb', 'a\u202eb', 'a\u2066b', 'a\x00b']:
            self.invoke(dict(command='text.hyphenate', rules={}, words=['valid', word]), 'INVALID_HYPHENATION')

    def test_storage_and_matching_work_limits(self):
        request_limit = self.invoke(dict(command='capabilities'))['limits']['request_bytes']
        cases = [({}, ['a'*257]), ({}, ['a']*257), ({}, ['a'*256]*17), (dict(patterns=[pattern('a'*65, [0]*66)]), []), (dict(patterns=[pattern('a', [0, 0])]*32769), []), (dict(patterns=[pattern('a'*64, [0]*65)]*4097), []), (dict(exceptions={str(i): [] for i in range(4097)}), []), (dict(exceptions={str(i).zfill(256): [] for i in range(257)}), [])]
        for rules, words in cases:
            with self.subTest(words=len(words), patterns=len(rules.get('patterns', []))):
                request = dict(command='text.hyphenate', rules=rules, words=words)
                expected = 'REQUEST_TOO_LARGE' if len(json.dumps(request).encode()) > request_limit else 'RESOURCE_LIMIT'
                self.invoke(request, expected)
        # Every prefix matches, so the total of weight overlays exceeds the shared budget.
        rules = dict(patterns=[pattern('a'*n, [1]*(n+1)) for n in range(1, 65)])
        self.invoke(dict(command='text.hyphenate', rules=rules, words=['a'*256]*16), 'RESOURCE_LIMIT')
        self.assertEqual(len(self.inspect({}, ['a'*256]*16)['words']), 16)

    def test_deadline_and_cancel_marker_leave_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp)/'cancel'; marker.write_bytes(b'original-marker')
            self.invoke(dict(command='text.hyphenate', rules={}, words=['abc'], control=dict(cancel_file=str(marker))), 'CANCELLED')
            self.assertEqual(marker.read_bytes(), b'original-marker')
        self.invoke(dict(command='text.hyphenate', rules={}, words=['abc'], control=dict(timeout_ms=0)), 'TIMEOUT')

    def test_schema_capability_and_mcp_readonly_parity(self):
        caps = self.invoke(dict(command='capabilities'))
        self.assertIn('text.hyphenate', caps['commands']); self.assertFalse(caps['hyphenation']['layout_integration'])
        self.assertEqual(caps['hyphenation']['word_scalars'], 256)
        with closing(Client()) as client:
            client.initialize(); found = []
            cursor = None
            while True:
                page = client.rpc('tools/list', {} if cursor is None else dict(cursor=cursor))['result']
                found.extend(page['tools']); cursor = page.get('nextCursor')
                if cursor is None: break
            tool = next(t for t in found if t['name'] == 'inkbolt_text_hyphenate')
            self.assertTrue(tool['annotations']['readOnlyHint']); self.assertFalse(tool['annotations']['openWorldHint'])
            rules = dict(min_left=1, min_right=1, patterns=[pattern('abcd', [0, 1, 0, 1, 0])])
            result = client.tool('text.hyphenate', rules=rules, words=['abcd'])['structuredContent']
            self.assertTrue(result['ok']); self.assertEqual(result['result'], self.inspect(rules, ['abcd']))
            error = client.tool('text.hyphenate', rules=dict(min_left=0), words=['abcd'])['structuredContent']
            self.assertEqual(error['error']['code'], 'INVALID_HYPHENATION')


if __name__ == '__main__':
    unittest.main()
