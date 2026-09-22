import unittest
from factory_ng_queue_tracking import measure, window_trend

class QueueTrackingTest(unittest.TestCase):
    def test_dispatch_changes_waiting_but_does_not_count_as_drain(self):
        a=measure({'a':{'state':'awaiting_verification'}},epoch=1)
        b=measure({'a':{'state':'working','verification_resume':True}},a,epoch=61)
        self.assertEqual((b['waiting'],b['running'],b['net_unfinished_change']),(0,1,0))
        self.assertEqual(b['completed'],[])

    def test_failure_and_supersession_are_distinct_from_completion(self):
        a=measure({k:{'state':'awaiting_verification'} for k in ['a','b','c']},epoch=1)
        b=measure({'a':{'state':'completed'},'b':{'state':'failed'},
                   'c':{'state':'blocked','superseded_by':'next'}},a,epoch=61)
        self.assertEqual(b['completed'],['a'])
        self.assertEqual(b['departed_without_completion'],{'b':'failed','c':'superseded'})
        self.assertEqual(b['cohort_states'],{'completed':1,'failed':1,'superseded':1})

    def test_arrivals_can_mask_successful_completion(self):
        a=measure({'a':{'state':'integrating'}},epoch=1)
        b=measure({'a':{'state':'completed'},'b':{'state':'awaiting_integration'}},a,epoch=61)
        self.assertEqual(b['net_unfinished_change'],0)
        self.assertEqual(b['arrivals'],['b']);self.assertEqual(b['completed'],['a'])
        c=measure({'a':{'state':'completed'},'b':{'state':'integrating'}},b,epoch=121)
        self.assertEqual(c['completed_since_baseline'],1);self.assertEqual(c['completed'],[])

    def test_growth_alert_needs_a_measured_window_and_more_unfinished_work(self):
        a=measure({str(i):{'state':'awaiting_verification'} for i in range(20)},epoch=1)
        b=measure({str(i):{'state':'integrating'} for i in range(25)},a,epoch=1801)
        trend=window_trend(b,[a]);self.assertTrue(trend['growth_alert'])
        self.assertEqual(trend['unfinished_change'],5)
        b['epoch']=61;self.assertFalse(window_trend(b,[a])['growth_alert'])
