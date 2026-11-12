import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('retrieval_gaps', Path(__file__).resolve().parents[1] / 'tools/retrieval_gaps.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class RetrievalGapsTests(unittest.TestCase):
    def trace(self, **stages):
        return {'query_id': 'Q1', 'index_version': 'snapshot1', 'retrieval_version': 'v1', 'stages': stages}

    def test_no_rows_count_zero_of_ten(self):
        r = M.diagnose({'id': 'Q1', 'returned': 0}, self.trace(index_hits=[], returned=[]))
        self.assertEqual((r['zero_reason'], r['fixed_slot_precision'], r['missing_top10_slots']), ('no_index_hit', 0, 10))

    def test_unknown_not_guessed_from_zero_summary(self):
        r = M.diagnose({'query_id': 'Q1', 'returned': 0})
        self.assertEqual(r['zero_reason'], 'unknown_uninstrumented')
        self.assertIsNone(r['relevant_top10'])

    def test_filter_and_sector_have_different_evidence(self):
        for stages, reason in [({'index_hits': ['a'], 'after_filters': [], 'returned': []}, 'filter_removed_all'),
                               ({'index_hits': ['a'], 'after_filters': ['a'], 'after_sector': [], 'returned': []}, 'sector_removed_all')]:
            self.assertEqual(M.diagnose({'id': 'Q1'}, self.trace(**stages))['zero_reason'], reason)

    def test_language_needs_evidence(self):
        t = self.trace(index_hits=[], returned=[])
        t['language_blocked'] = True
        self.assertEqual(M.diagnose({'id': 'Q1'}, t)['zero_reason'], 'no_index_hit')
        t['language_evidence'] = 'translation unavailable'
        self.assertEqual(M.diagnose({'id': 'Q1'}, t)['zero_reason'], 'language_blocked')

    def test_partial_unknown_and_unlabelled_never_become_hits(self):
        labels = [{'query_id': 'Q1', 'supplier_id': s, 'label': l, 'in_index': True}
                  for s, l in [('a', 'relevant'), ('b', 'partly'), ('c', 'cannot_tell')]]
        r = M.diagnose({'id': 'Q1'}, self.trace(returned=['a', 'b', 'c', 'd']), labels)
        self.assertEqual((r['relevant_top10'], r['judged_top10'], r['unlabelled_top10'], r['cannot_tell_top10']), (1, 2, 1, 1))
        self.assertEqual((r['fixed_slot_precision'], r['judged_precision']), (.1, .5))

    def test_sample_availability_and_recall_use_stable_ids(self):
        labels = [{'query_id': 'Q1', 'supplier_id': s, 'label': 'relevant', 'in_index': True} for s in ['a', 'b']]
        r = M.diagnose({'id': 'Q1'}, self.trace(returned=['a']), labels)
        self.assertEqual((r['labelled_relevant_in_index'], r['labelled_sample_recall']), (2, .5))

    def test_index_availability_not_inferred_from_labels(self):
        r = M.diagnose({'id': 'Q1'}, self.trace(returned=['a']), [{'query_id': 'Q1', 'supplier_id': 'a', 'label': 'relevant'}])
        self.assertIsNone(r['labelled_relevant_in_index'])

    def test_absent_supplier_cannot_be_returned(self):
        with self.assertRaises(ValueError):
            M.diagnose({'id': 'Q1'}, self.trace(returned=['a']), [{'query_id': 'Q1', 'supplier_id': 'a', 'label': 'relevant', 'in_index': False}])

    def test_stage_expansion_or_duplicates_rejected(self):
        for stages in [{'index_hits': ['a'], 'returned': ['b']}, {'returned': ['a', 'a']}]:
            with self.assertRaises(ValueError):
                M.diagnose({'id': 'Q1'}, self.trace(**stages))

    def test_count_disagreement_rejected(self):
        with self.assertRaises(ValueError):
            M.diagnose({'id': 'Q1', 'returned': 0}, self.trace(returned=['a']))

    def test_rank_only_or_duplicate_labels_rejected(self):
        row = {'query_id': 'Q1', 'supplier_id': 'a', 'label': 'relevant'}
        for labels in [[{'query_id': 'Q1', 'rank': 1, 'label': 'relevant'}], [row, row]]:
            with self.assertRaises(ValueError):
                M.diagnose({'id': 'Q1'}, self.trace(returned=['a']), labels)

    def test_holdout_trace_and_labels_rejected(self):
        for args in [([{'query_id': 'Q2'}], []), ([], [{'query_id': 'Q2'}])]:
            with self.assertRaises(ValueError):
                M.build([{'id': 'Q1'}], {'tune': ['Q1'], 'heldout': ['Q2']}, *args)

    def test_missing_requests_do_not_reduce_denominator(self):
        r = M.build([{'id': 'Q1'}, {'id': 'Q3'}], {'tune': ['Q1', 'Q2'], 'heldout': ['Q3']})
        self.assertEqual((r['top10_denominator'], r['missing_development_requests']), (20, ['Q2']))
        self.assertEqual([x['query_id'] for x in r['per_request']], ['Q1'])

    def test_bad_manifest_and_duplicate_requests_rejected(self):
        for req, manifest in [([{'id': 'Q1'}], {'tune': ['Q1'], 'heldout': ['Q1']}),
                              ([{'id': 'Q1'}, {'id': 'Q1'}], {'tune': ['Q1']})]:
            with self.assertRaises(ValueError):
                M.build(req, manifest)

    def test_records_support_existing_summary_shapes(self):
        for obj in [{'per_request': {'Q1': {'returned': 0}}}, {'product': {'per_query': [{'query_id': 'Q1'}]}},
                    {'per_query': [{'query_id': 'Q1'}]}]:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / 'summary.json'
                p.write_text(json.dumps(obj))
                self.assertEqual(M.qid(M.records(p)[0]), 'Q1')

    def test_ast_request_loading_cannot_execute_config_or_network(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'search_eval.py'
            p.write_text("raise RuntimeError('never execute')\nCASES=[('S01','s','x','x',''),('T01','t','y','y','')]\n")
            self.assertEqual(M.records(p), [{'query_id': 'S01'}])

    def test_private_names_not_echoed_in_diagnostics(self):
        r = M.diagnose({'id': 'Q1', 'query': 'private query'}, self.trace(returned=['private supplier']))
        self.assertNotIn('private', json.dumps(r))

    def test_cli_writes_private_file_but_prints_counts_only(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/'m.json').write_text(json.dumps({'tune': ['Q1']}))
            (td/'r.json').write_text(json.dumps([{'id': 'Q1', 'returned': 0}]))
            M.main(['--manifest', str(td/'m.json'), '--requests', str(td/'r.json'), '--out', str(td/'out.json')])
            self.assertTrue(json.loads((td/'out.json').read_text())['development_only'])


if __name__ == '__main__':
    unittest.main()
