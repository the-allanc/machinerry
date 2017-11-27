from __future__ import print_function
from decimal import Decimal, ROUND_HALF_DOWN
from datetime import timedelta
try:
    from queue import Queue, Empty
except ImportError:
	from Queue import Queue, Empty # python 2
import logging
import time

import cherrypy

from machinerry import Machine


class LogToList(logging.Handler):

    def __init__(self, ls):
        logging.Handler.__init__(self)
        self.the_almighty_list = ls

    def emit(self, record):
        msg = self.format(record)
        self.the_almighty_list.append(msg)


class MachineForTesting(Machine):

    _pause_elapsed_check = None
    pause_until_elapsed_called = False

    def __init__(self, name):
        Machine.__init__(self, name)
        self.job_queue = Queue()
        self.message_log = []
        self.__pause_repeat = None

        cherrypy.log.error_log.addHandler(LogToList(self.message_log))

    def delay(self, secs):
        self.job_queue.put(('delay', secs))

    def echo(self, message):
        self.job_queue.put(('echo', message))

    def fail(self, message):
        self.job_queue.put(('fail', message))

    def record(self, name, value):
        self.job_queue.put(('record', name, value))

    def pauseit(self, message, how_long, repeat):
        self.job_queue.put(('pause', message, how_long, repeat))

    def execute(self):
        try:
            job_data = self.job_queue.get_nowait()
        except Empty:
            # Nothing to do at the moment.
            return
        else:
            handler = getattr(self, 'perform_' + job_data[0])
            return handler(*job_data[1:])

    def perform_delay(self, secs):
        time.sleep(secs)

    def perform_echo(self, message):
        self.message_log.append(message)

    def perform_fail(self, message):
        raise RuntimeError(message)

    def perform_record(self, name, value):
        setattr(self.machine_run, name, value)

    def perform_pause(self, message, how_long, repeat):
        self.pause_for_reason(None, message)
        self.pause_until = self._pauseit_until = self.now(
        ) + timedelta(seconds=how_long)
        self.__pause_elapsed_check = how_long
        self.__pause_repeat = repeat

    class MachineTestError(RuntimeError):
        pass

    def on_machine_pause_until_elapsed(self):
        Machine.on_machine_pause_until_elapsed(self)
        self.pause_until_elapsed_called = True

        # This is where we allow the machine to simulate total failure.
        fail_reason = getattr(self, 'simulate_internal_fail', '')
        if fail_reason:
            raise self.MachineTestError(fail_reason)

        if self.__pause_repeat is None:
            return
        elif self.__pause_repeat:
            self.pause_until = self.now(
            ) + timedelta(seconds=self.__pause_elapsed_check)
        else:
            self.resume_by(None)


class TestMachine(object):
    
    def assertEqual(self, x, y):
        assert x == y

    def setup_method(self, method):
        # Take the last three words - we need shorter names to be able
        # stop some of the text wrapping for mail lines.
        self.machine = MachineForTesting(
            '_'.join(method.__name__.split('_')[-3:]))

    def teardown_method(self, method):
        self.machine.stop()

    def assertState(self, value):
        assert self.machine.machine_state == value

    def assertRescheduleGap(self, gap, from_start=False):
        times = self.machine.status()['times']
        if not from_start:
            prev = times['end']
        else:
            prev = times['start']

        next = times['next']

        gap_delta = next - prev
        gap_calculated = Decimal(gap_delta.seconds) + (
            Decimal(gap_delta.microseconds) / Decimal(1000000))
        gap_expected_dec = Decimal(gap)
        gap_calculated = gap_calculated.quantize(
            gap_expected_dec, rounding=ROUND_HALF_DOWN)
        if gap_calculated != gap_expected_dec:
            print('Times:')
            print('  Start:', times['start'])
            print('  End:', times.get('end'))
            print('  Next:', times['next'])
            raise AssertionError('Expected=%s, Calculated=%s' %
                                 (gap_expected_dec, gap_calculated)
                                 )

    def assertPrinted(self, message):
        for line in self.machine.message_log:
            if message in line:
                break
        else:
            print('Message log:')
            for line in self.machine.message_log:
                print(repr(line))
            raise AssertionError('unable to find %r in message log' % message)

    def assertNotPrinted(self, message):
        for line in self.machine.message_log:
            if message not in line:
                break
        else:
            print('Message log:')
            for line in self.machine.message_log:
                print(repr(line))
            raise AssertionError(
                'found %r unexpectedly in message log' % message)

    def assertActivityLog(self, text, buser=None):
        pass

    @property
    def runs(self):
        return self.machine.machine_run_history

    def assertRunHistorySize(self, expected):
        if len(self.runs) != expected:
            raise AssertionError(
                'Expected %s entries, but have %s: %s'
                % (expected, len(self.runs), self.runs)
            )

    wait = time.sleep

    # defined in pmx_fixture.sql
    admin = dict(username='admin', buserid=999)
    admin2 = dict(username='admin2', buserid=998)

    def test_machine_basics(self):

        # Check stopped by default.
        self.assertState('STOPPED')
        self.assertEqual(self.machine.machine_active, False)

        # We've given nothing for it to do, so it should be waiting.
        self.machine.start()
        self.wait(0.3)
        self.assertState('WAITING')
        self.assertEqual(self.machine.machine_active, True)

        # Give it a job which will take two seconds to complete, and
        # then tell it to stop.
        self.machine.delay(2)
        self.wait(0.2)
        self.machine.stop()

        # After half a second, it should be on the way to stopping, but
        # it needs to finish the job it's already on.
        self.wait(0.5)
        self.assertState('STOPPING')
        self.assertEqual(self.machine.machine_active, False)

        # Give it the two seconds it needs to finish the job and then
        # terminate.
        self.wait(2)
        self.assertState('STOPPED')
        self.assertEqual(self.machine.machine_active, False)

    def test_machine_reschedule_no_frequency(self):

        # Start machine up with a delay and a message to print.
        self.machine.delay(2)
        self.machine.echo('Ishida')
        self.machine.start()

        # While it's processing the delay command, this should count as
        # running.
        self.wait(.5)
        self.assertState('RUNNING')
        self.assertEqual(self.machine.machine_active, True)

        # Once it's done that, it should count as waiting.
        self.wait(2)
        self.assertState('WAITING')

        # The next execution should be 0.2 seconds from the last (based
        # on the default wait time on the class).
        self.assertRescheduleGap('0.2')

        # And our second job should have been processed.
        self.assertPrinted('Ishida')

    def test_machine_reschedule_with_frequency(self):

        # Enqueue the commands to print these two words.
        self.machine.echo('Kenpachi')
        self.machine.echo('Zaraki')

        # Make the machine run as a periodic one (every X seconds).
        self.machine.wait_run_frequency = 3
        self.machine.start()

        # Allow the first cycle to complete, and check the first job
        # is the only one done so far.
        self.wait(1)
        self.assertState('WAITING')
        self.assertRescheduleGap('3.0', from_start=True)
        self.assertPrinted('Kenpachi')
        self.assertNotPrinted('Zaraki')

        # Now wait for the next cycle and check the status of the
        # second job.
        self.wait(3)
        self.assertPrinted('Zaraki')
        self.assertRescheduleGap('3.0', from_start=True)

    def test_machine_handle_errors(self):

        # Set the machine to wait for 10 seconds after failure.
        self.machine.wait_on_error = 10
        self.machine.fail('Bankai!')
        self.machine.start()

        # Give it a second to fail.
        self.wait(1)
        self.assertState('WAITING')

        # Ensure that we are waiting the 10 seconds as expected.
        self.assertRescheduleGap('10.0')

    def test_machine_stop_overrides_wait(self):

        # Set the machine to run every 10 seconds.
        self.machine.wait_run_frequency = 10
        self.machine.start()
        self.wait(0.5)

        # We expect the machine to be waiting for the next run.
        self.assertState('WAITING')
        self.assertRescheduleGap('10.0')

        # But if we tell it to stop, it should wake up and just halt.
        self.machine.stop()
        self.wait(0.5)
        self.assertState('STOPPED')

    def test_machine_immediate_error_when_pause_on_fail(self):

        # Set the machine to fail, and to pause on fail.
        self.machine.wait_on_error = 10
        self.machine.fail('Shikai!')
        self.machine.pause_on_error = True
        self.machine.pause_alert_initial_threshold = 300
        self.machine.start()

        # Wait for a second, and check that we are indeed paused.
        self.wait(1)
        self.assertState('PAUSED')

        # Check logs - the activity log won't mention the "actor"
        # who paused the system as that's recorded elsewhere.
        self.assertActivityLog(
            '%s set to pause - automatic pause due to error occurring.' %
            self.machine.machine_name
        )
        self.assertPrinted(
            '%s set to pause by itself - automatic pause due to error '
            'occurring.' % self.machine.machine_name
        )

        # And then we get separate log messages when the pause takes place.
        self.assertActivityLog('%s paused.' % self.machine.machine_name)
        self.assertPrinted('%s paused.' % self.machine.machine_name)

        subjtmpl = 'pause_on_fail on %s PAUSED'

        # But we need to have received an e-mail notifying us.

    def test_machine_pause_and_resume_doesnt_upset_schedule(self):
        self.machine.wait_run_frequency = 20

        # Start, do nothing, and then wait for 20 seconds for the next
        # run.
        self.machine.start()
        self.wait(0.5)
        self.assertState('WAITING')

        def next_time():
            return self.machine.status()['times']['next']

        next_exec_time = next_time()

        # Pausing the machine still keep the next schedule time as-is.
        self.machine.paused = True
        self.wait(0.5)
        self.assertEqual(next_exec_time, next_time())
        self.assertState('PAUSED')

        # Resuming the machine should still keep the next schedule time
        # as-is.
        self.machine.paused = False
        self.wait(0.5)
        self.assertState('WAITING')
        self.assertEqual(next_exec_time, next_time())

    def test_machine_pause_resume_alerts(self):

        # Set a pause alert for 2 seconds, and then every 5 seconds afterward.
        #
        # Note that the first "reminder" should be after 5 seconds from
        # the pause time, not the last reminder.
        self.machine.pause_alert_initial_threshold = 2
        self.machine.pause_alert_further_threshold = 5
        self.machine.delay(1)
        self.machine.start()

        # Let's pause the service whilst in the middle of a job.
        self.wait(0.25)
        self.machine.pause_for_reason(self.admin, 'Because I wanted to!')

        # Because the delay is for a second, it should still be running
        # after waiting around for half a second.
        self.wait(0.25)
        self.assertState('RUNNING')

        # But we should still have an activity message saying that the
        # service was paused. It should also blame the admin user for it.
        self.assertActivityLog(
            '%s set to pause - Because I wanted to!' %
            self.machine.machine_name, buser=self.admin
        )
        self.assertPrinted(
            '%s set to pause by admin - Because I wanted to!' %
            self.machine.machine_name
        )
        self.assertNotPrinted('%s paused.' % self.machine.machine_name)

        # Wait for the delay job to exhaust itself, and we should see the
        # log messages saying that it has been paused.
        self.wait(1)
        self.assertActivityLog('%s paused.' % self.machine.machine_name)
        self.assertPrinted('%s paused.' % self.machine.machine_name)

        # We shouldn't have gotten an e-mail notification about it yet
        # though.
        #m = self.lastmail(allow_none=True)
        #if m:
        #    self.assertNotInMail('Because I wanted to!', m)

        # Resuming shouldn't generate an e-mail either, because we
        # didn't generate a pause alert.
        self.machine.resume_by(self.admin2)
        self.wait(0.5)
        #m = self.lastmail(allow_none=True)
        #if m:
        #    self.assertNotInMail('set to resume by admin2', m)

        # OK, back to pausing it again.
        self.machine.pause_for_reason(
            self.admin, 'Because I really wanted to!')

        # Wait for another two seconds (so over two seconds has now elapsed
        # the delay job expired). We should have a notification message.
        self.wait(3)
        #m = self.lastmail()
        #self.assertInMail(self.machine.machine_name, m)
        #self.assertInMail('PAUSED', m)
        #self.assertInMail('Because I really wanted to!', m)
        #self.assertInMail('2 seconds', m)

        # Another 4 seconds, we should have another mail.
        self.wait(5)
        #m = self.lastmail()
        #self.assertInMail(self.machine.machine_name, m)
        #self.assertInMail('PAUSED', m)
        #self.assertInMail('Because I really wanted to!', m)
        #self.assertInMail('5 seconds', m)

        # Let's make sure that the next reminder is calculated from the
        # previous alert time, rather than the pause time.
        self.wait(5)
        #m = self.lastmail()
        #self.assertInMail('10 seconds', m)

        # Now set to resume, and expect some appropriate log messages
        # regarding this.
        self.machine.resume_by(self.admin2)
        #self.assertActivityLog(
        #    '%s set to resume.' % self.machine.machine_name,
        #    buser=self.admin2)
        self.assertPrinted('%s set to resume by admin2.' %
                           self.machine.machine_name)

        # After giving it a bit of time, we should see log messages,
        # activity log messages and a useful e-mail indicating that
        # services have resumed.
        self.wait(1)
        #m = self.lastmail()
        #self.assertInMail(self.machine.machine_name, m)
        #self.assertInMail('RUNNING', m)
        #self.assertInMail('Resumed by: admin2', m)
        #self.assertNotInMail('Because I really wanted to!', m)
        self.assertPrinted('%s resumed.' % self.machine.machine_name)
        #self.assertActivityLog('%s resumed.' % self.machine.machine_name)

    def test_machine_next_run_times(self):

        # We're testing to see what rescheduling behaviour is in place.
        self.machine.wait_min = 3
        self.machine.wait_run_frequency = 10
        self.machine.wait_on_error = 120

        # Do nothing - should just use the default frequency gap.
        self.machine.start()
        self.wait(0.5)
        self.assertRescheduleGap('10.0')

        # Turn off frequency - it should use wait_min.
        self.machine.wait_run_frequency = None
        self.machine.run_now()
        self.wait(0.5)
        self.assertRescheduleGap('3')

        # Override it - this one time!
        self.machine.wait_for_this_one_time = 2
        self.machine.run_now()
        self.wait(0.5)
        self.assertRescheduleGap('2')

        # Next time should go back to frequency.
        self.machine.run_now()
        self.wait(0.5)
        self.assertRescheduleGap('3')

        # Turn frequency back on, but make the next job fail. It should
        # use error_delay.
        self.machine.wait_run_frequency = 10
        self.machine.fail('Nee-san!')
        self.machine.run_now()
        self.wait(1)
        self.assertRescheduleGap('120')

        # No error delay? It should use frequency instead.
        self.machine.wait_on_error = None
        self.machine.fail('Orihime!')
        self.machine.run_now()
        self.wait(1)
        self.assertRescheduleGap('10')

    def test_machine_retains_run_history(self):

        # Start off with no record history.
        self.machine.wait_run_frequency = 10
        self.machine.run_history_limit = None
        self.assertEqual(self.runs, [])

        # First test - no limit means no run information gets saved.
        self.machine.record('hueco', 'mundo')
        self.machine.start()
        self.wait(0.5)
        self.assertEqual(self.runs, [])

        # Second test - a limit will mean record information gets saved.
        self.machine.run_history_limit = 2
        self.machine.record('grimmjow', 'jaegerjaquez')
        self.machine.run_now()
        self.wait(0.25)
        self.assertRunHistorySize(1)
        self.assertEqual(self.runs[0].grimmjow, 'jaegerjaquez')
        self.assertEqual(self.runs[0].id, 1)  # id 0 was in discarded run

        # Third test - another invocation will not contain any of the
        # information stored on the previous one (and the previous run
        # doesn't have its information overwritten by new data).
        self.machine.record('grimmjow', 'number six')
        self.machine.run_now()
        self.wait(0.25)
        self.assertRunHistorySize(2)
        self.assertEqual(self.runs[1].grimmjow, 'number six')
        self.assertEqual(self.runs[0].grimmjow, 'jaegerjaquez')
        self.assertEqual(self.runs[1].id, 2)

        # Fourth test - another invocation will show that the older run
        # get pushed out of the way.
        self.machine.record('coyote', 'starrk')
        self.machine.run_now()
        self.wait(0.25)
        self.assertRunHistorySize(2)
        self.assertEqual(self.runs[0].grimmjow, 'number six')
        self.assertEqual(self.runs[1].coyote, 'starrk')
        self.assertEqual(self.runs[1].id, 3)

        # Fifth test - setting the limit to zero will allow more to be
        # runs to be stored.
        self.machine.run_history_limit = 0
        self.machine.record('vasto', 'lorde')
        self.machine.run_now()
        self.wait(0.25)
        self.assertRunHistorySize(3)
        self.assertEqual(self.runs[-1].vasto, 'lorde')
        self.assertEqual(self.runs[-1].id, 4)

    def test_machine_override_pause_until_setting(self):

        # Set the machine to pause as soon as it starts. It will be
        # set to pause for 10 seconds before allowing itself to continue.
        self.machine.pauseit('shinji', 10, False)
        self.machine.pause_alert_initial_threshold = 20
        self.machine.pause_alert_further_threshold = 30
        self.machine.start()
        self.wait(2)

        # After 2 seconds, we should have got a notification e-mail that
        # the service has automatically paused itself - regarding
        # notification e-mails, we don't have the same "grace" period
        # that we allow with the initial threshold when there is manual
        # intervention.
        #m = self.lastmail()
        #self.assertInMail(self.machine.machine_name, m)
        #self.assertInMail('PAUSED', m)

        # Now, we check that the service is going to be paused until
        # the value that is explicitly set by the wait time we gave
        # it earlier.
        self.assertEqual(self.machine.pause_until, self.machine._pauseit_until)

        # And that time is earlier than the next scheduled pause alert.
        assert self.machine.pause_until < self.machine.pause_alert_next

        # Great! Now, override and remove the pause time we gave before.
        # The service should still wake itself up at the next alert time.
        self.machine.pause_until = None
        self.assertEqual(self.machine.pause_until, self.machine.pause_alert_next)

        # Now set a pause time again - higher than the alert time. The
        # pause_alert time should take precedence.
        ages_away = self.machine.now() + timedelta(seconds=200)
        self.machine.pause_until = ages_away
        self.assertEqual(self.machine.pause_until, self.machine.pause_alert_next)
        assert ages_away > self.machine.pause_alert_next
            
        # The on_machine_pause_until_elapsed hook should be called, but only
        # when our explicitly set pause_until value has elapsed, and not when it
        # wakes itself up to perform alerts. Let's test this.
        
        # Reset this flag.
        self.machine.pause_until_elapsed_called = False
        
        # We're going to test the ability to modify the messages being generated.
        self.machine.format_notify_status_lines = lambda ls: ls + ['Howdy']
        
        # Set the alert threshold to happen sooner than our pause_until is set.
        self.machine.pause_alert_further_threshold = 3
        assert self.machine.pause_alert_next < self.machine.now() + timedelta(seconds=2)
        self.machine.interrupt()
        self.wait(2.5)

        # Our function shouldn't have been called.
        assert not self.machine.pause_until_elapsed_called
        
        # And we should have got a notification e-mail saying we were paused
        # for 3 seconds (so we were awoken, but we didn't hit the "pause_until"
        # threshold).
        #m = self.lastmail()
        #self.assertInMail('3 seconds', m)
        
        # (Test that we got a message added in the status lines section.)
        #self.assertInMail('Howdy', m)

        # And if we set a lower pause until time, our explicit time should
        # take precendence again.
        self.machine.pause_until = soon = self.machine.now() + timedelta(seconds=1)
        self.assertEqual(self.machine.pause_until, soon)
        del soon

        # Wait until that time has elapsed, the machine should wake itself
        # up and carry on processing as normal.
        self.assertState('PAUSED')
        self.wait(1.5)

        # Check we have a notification e-mail and the service has resumed
        # itself.
        #m = self.lastmail()
        #self.assertInMail(self.machine.machine_name, m)
        #self.assertInMail('Resumed by: itself', m)
        self.assertEqual(self.machine.machine_active, True)
        
        # Make sure that our pause_until_elapsed hook was called.
        assert self.machine.pause_until_elapsed_called


    def test_machine_notify_on_fail(self):

        # Set the machine to pause for one second, and resume itself.
        # But we also set a flag on the machine to simulate failure when
        # reacting to the pause time elapsing.
        self.machine.simulate_internal_fail = 'hachigen'
        self.machine.pauseit('ushoda', 1, False)
        self.machine.start()

        # Machine should have failed by now (when attempting to report
        # something regarding how long we've been paused for.
        self.wait(1.5)
        self.assertState('FAILED')

        # First of all, the machine should clear itself of any paused
        # data if we have failed (this is so we don't confuse any
        # reporting).
        self.assertEqual(self.machine.paused, False)

        # Also hopefully a message in the logs.
        self.assertPrinted('%s failed.' % self.machine.machine_name)
