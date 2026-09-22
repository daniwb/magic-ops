import unittest

from factory_ng_frontier_reserve import pending_frontier, reconcile_reserve


class FrontierReserveTests(unittest.TestCase):
    def jobs(self):
        return {str(i): {'state': 'queued', 'production': {'producer': 'corpus-frontier'}, 'rank': i}
                for i in range(20)}

    def test_deferred_inventory_consumes_frontier_admission(self):
        jobs = self.jobs()
        self.assertEqual(pending_frontier(jobs), 20)
        reconcile_reserve(jobs, 3, lambda item: item[1]['rank'], 'now')
        self.assertEqual(sum(j['state'] == 'queued' for j in jobs.values()), 3)
        self.assertEqual(pending_frontier(jobs), 20)
        self.assertEqual([key for key, job in jobs.items() if job['state'] == 'queued'], ['0', '1', '2'])

    def test_completion_promotes_next_without_new_ticket_or_attempt(self):
        jobs = self.jobs()
        reconcile_reserve(jobs, 3, lambda item: item[1]['rank'], 'now')
        jobs['0']['state'] = 'completed'
        reconcile_reserve(jobs, 3, lambda item: item[1]['rank'], 'later')
        self.assertEqual(jobs['3']['state'], 'queued')
        self.assertNotIn('attempts', jobs['3'])
        self.assertEqual(len(jobs), 20)

    def test_preserves_attempted_work_and_other_producers(self):
        jobs = self.jobs()
        jobs['0'].update(attempts=1, receipt='failed-receipt')
        jobs['other'] = {'state': 'queued', 'rank': 99}
        jobs['working'] = {'state': 'working', 'pid': 42}
        reconcile_reserve(jobs, 3, lambda item: item[1]['rank'], 'now')
        self.assertEqual(jobs['0']['state'], 'queued')
        self.assertEqual(jobs['0']['attempts'], 1)
        self.assertEqual(jobs['other']['state'], 'queued')
        self.assertEqual(jobs['working']['pid'], 42)
        self.assertEqual(jobs['1']['state'], 'queued')
        self.assertEqual(jobs['2']['state'], 'backlog')

    def test_failed_superseded_and_blocked_do_not_consume_admission(self):
        jobs = self.jobs()
        for i, state in enumerate(('failed', 'blocked', 'completed', 'parked')):
            jobs[str(i)]['state'] = state
        jobs['4']['superseded_by'] = 'next'
        self.assertEqual(pending_frontier(jobs), 15)


if __name__ == '__main__':
    unittest.main()
