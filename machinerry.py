import cherrypy
import threading


import datetime
_utcnow = datetime.datetime.utcnow


# Simple namespace to store run-specific information.


class Run(dict):

    def __init__(self):
        self.time_start = None
        self.time_end = None
        self.time_next = None
        self.failed = False
        self.pause_flag_set = False

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)

    def __setattr__(self, attr, val):
        self[attr] = val

    def __delattr__(self, attr):
        try:
            del self[attr]
        except KeyError:
            raise AttributeError(attr)


class BoneMachine(object):

    """Internal subclass which provides the bulk of the machine framework.

    You should use the Machine class directly."""

    # Valid states.
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    WAITING = 'WAITING'
    STOPPING = 'STOPPING'
    STOPPED = 'STOPPED'
    FAILED = 'FAILED'

    # How long to wait for before executing the next run if an error
    # occurs. If set, then this is used regardless of whether
    # wait_run_frequency is set.
    wait_on_error = None

    # The minimum amount of time to wait between the last run and the
    # next run.
    wait_min = 0.2

    # How often to perform the next run based on the start of the last
    # run.
    wait_run_frequency = None

    # You can set a specific time to wait for after a particular run.
    #
    # This will override the other wait values, and will be set to
    # None after the run has finished.
    wait_for_this_one_time = None

    # The time that the current run (or the previous run) started.
    run_time_start = None

    # The time that the previous run ended (or None if the current run
    # hasn't yet finished).
    run_time_end = None

    # The time that the next run is scheduled to run. Should be set only
    # when we are not in the middle of a run.
    run_time_next = None

    # How many run objects we record in the "runs" attribute. By default,
    # this is set to None, meaning no records get stored. If zero - this
    # means no limit.
    run_history_limit = None

    # How many run objects have we created so far?
    _run_count = 0

    # The current state of the machine execution.
    machine_state = STOPPED

    # When did the machine start execution?
    machine_up_since = None

    # Internal pause flag - use 'paused' instead.
    _paused = False

    # The datetime of when the machine should remain paused until.
    #
    # This value should be set when the machine either:
    #   a) has it's paused flag set; or
    #   b) becomes paused (you can detect this by overriding on_machine_pause).
    #
    # If the machine remains paused until this time, it will trigger
    # on_machine_pause_elapsed. When subclasses override this function,
    # they must do one of the following two things:
    #   a) unpause the machine; or
    #   b) extend the time to a later date.
    #
    pause_until = None

    # The datetime of when the machine went into pause mode.
    pause_time = None

    # Flag indicating whether the machine should automatically pause
    # itself if an error occurs when invocating 'execute'.
    #
    # If you want to react to this type of event, you should set this
    # flag to True and then override on_machine_pause_due_to_error.
    pause_on_error = False

    def _get_paused(self):
        return self._paused

    def _set_paused(self, state):
        self._paused = state

        # Detect if we were changed by the machine thread, and if we
        # were in the execute block (we can verify with the existence
        # of the _paused_by_execute attribute on the current machine_run).
        if threading.current_thread() is self.machine_thread and \
                hasattr(self.machine_run, '_paused_by_execute'):
            self.machine_run._paused_by_execute = state
        self.interrupt()

    paused = property(_get_paused, _set_paused, doc='''
        A flag to indicate if the machine should be paused or should
        be running. Setting it will not normally result in an immediate
        pause or resumption of execution, but it will take place as soon
        as is convenient.
    ''')

    @property
    def machine_active(self):
        return self.machine_state in (self.RUNNING, self.WAITING)

    @property
    def state_as_text(self):
        return self.machine_state.capitalize()

    def __init__(self, name):
        self.machine_name = name
        self.machine_thread = None
        self.machine_is_running = False
        self.machine_event_flag = threading.Event()
        self.machine_run_history = []

    def start(self):
        """Start processing in a new Thread."""
        if self.machine_thread is None:
            self.machine_thread = threading.Thread(target=self.run)
            self.machine_thread.name = ("%s thread" % self.machine_name)
            self.machine_thread.start()

    def stop(self):
        """Stop processing."""
        self.machine_is_running = False
        self.machine_thread = None
        self.machine_state = self.STOPPING
        self.interrupt()

    def now(self):
        return _utcnow()

    def run(self):
        """Continuously run self.execute(). Errors are trapped and logged."""
        try:
            try:
                get_ident = threading.get_ident
            except AttributeError:
                # noinspection PyProtectedMember
                # This is for Python 2 compatibility.
                get_ident = threading._get_ident  # pylint: disable=no-member
            self.machine_threadid = get_ident()
            self.machine_is_running = True
            self.machine_up_since = self.now()

            # Subclasses may choose to delay execution by setting
            # run_time_next manually.
            if self.run_time_next is None:
                self.run_time_next = self.machine_up_since

            while self.machine_is_running:
                now = self.now()
                self.machine_event_flag.clear()

                if self.paused:
                    self._become_paused(True)
                    if not self.pause_until:
                        self.machine_event_flag.wait(self.wait_min)
                        continue

                    # We've been asked to pause until a specific time.
                    self._wait_until(self.pause_until)
                    now = self.now()

                    # Been interrupted because we're now longer paused,
                    # so loop again!
                    if not self.paused:
                        continue

                    # We're still paused after the wait.
                    if self.pause_until <= now:
                        self.on_machine_pause_elapsed()
                        if self.paused and self.pause_until <= now:
                            e = 'still paused and not updating pause_until'
                            raise AssertionError(e)
                    continue

                # end-if self.paused block

                self._become_paused(False)

                if now < self.run_time_next:
                    self.machine_state = self.WAITING
                    self._wait_until(self.run_time_next)
                    continue

                self.machine_state = self.RUNNING
                self.run_once()

            # We trigger the pause mechanism (without changing the
            # state) to allow the machine to clear up.
            self.paused = True
            self._become_paused(True, set_state=False)

            # We may require something to make the machine to finally
            # stop - this is where subclasses can define what that is.
            self.on_machine_stopping()

            # Machine being brought to a halt.
            self.machine_state = self.STOPPED

        except Exception as e:
            self.machine_state = self.FAILED

            # If an exception occurs trying to report the machine
            # failure, just dump it to the log and let the original
            # exception take priority.

            # noinspection PyBroadException
            try:
                self.on_machine_fail(e)
            except Exception:
                # noinspection PyBroadException
                try:
                    cherrypy.log(traceback=True)
                except Exception:
                    pass

            raise

    # Helper function to make a thread sleep in a way that it can be
    # interrupted, using a timedelta as a way of expressing the time
    # to sleep.
    def _wait_until(self, dtime):
        self.machine_event_flag.wait(self._how_long_until(dtime))

    def _how_long_until(self, dt):
        now = self.now()
        if (now.tzinfo is None) != (dt.tzinfo is None):
            raise ValueError('cannot use mix of timezone-aware and '
                'timezone-naive datetimes')
        if now.tzinfo and now.tzinfo != dt.tzinfo:
            raise ValueError('must use same timezones')
        wait_time = dt - now
        return wait_time.seconds + (wait_time.microseconds / 1000000.0)

    def interrupt(self):
        '''Tell the execution thread to wake up.'''
        self.machine_event_flag.set()

    def run_now(self):
        '''Tell the execution thread to perform an execution now.'''
        self.run_time_next = self.now()
        self.interrupt()

    # Recalculates when the next run should be performed.
    def _reschedule(self, on_error):

        # Run times might be set by subclasses, so don't override
        # anything explicit.
        if self.run_time_next is not None:
            return

        for time, calc_from_now, use_it in [
            (self.wait_for_this_one_time, True, True),
            (self.wait_on_error, True, on_error),
            (self.wait_run_frequency, False, True),
            (self.wait_min, True, True),
        ]:
            if use_it and time is not None and time > 0:
                break

        if calc_from_now:
            self.run_time_next = self.run_time_end + \
                datetime.timedelta(seconds=time)
        else:
            self.run_time_next = self.run_time_start + \
                datetime.timedelta(seconds=time)

        # Invalidate wait_for_this_time if it was set.
        self.wait_for_this_one_time = None

    def __create_machine_run(self):
        # Prepare the run object.
        self.machine_run = run = Run()
        run.time_start = self.run_time_start
        run.id = self._run_count
        self._run_count += 1

        # Add it to the history list.
        if self.run_history_limit is not None:
            self.machine_run_history.append(run)
            if self.run_history_limit:
                self.machine_run_history = self.machine_run_history[
                    -self.run_history_limit:]  # pylint: disable=invalid-unary-operand-type

        return run

    def run_once(self):
        """Run self.execute() once. Errors are trapped.

        This is the equivalent of performing a single run immediately in
        the context of the machine (with regard to all the prep work which
        takes place around it). You should not execute this in a thread
        separate to the machine thread (unless that thread has ceased
        execution)."""
        self.run_time_start = self.now()
        self.run_time_end = None
        self.run_time_next = None

        run = self.__create_machine_run()

        res = None

        try:
            try:
                run._paused_by_execute = False
                res = self.execute()
            finally:
                self.run_time_end = run.time_end = self.now()
                paused_by_execute = run.pop('_paused_by_execute')
        except (KeyboardInterrupt, SystemExit):
            cherrypy.log("<Ctrl-C> hit: shutting down app engine", "ENGINE")
            self.stop()
            cherrypy.server.stop()
            cherrypy.engine.stop()
            raise
        except Exception as e:
            if self.pause_on_error:
                self.on_machine_pause_due_to_error(e)
            self.on_machine_error(e)
            self._reschedule(True)
            run.failed = True
        else:
            self._reschedule(False)

        # If the execute loop itself caused the service to pause, we
        # then set a flag on the run object and immediately set
        # ourselves to pause. This will also allow subclasses to react
        # immediately to internal pausing.
        if paused_by_execute:
            run.pause_flag_set = True
            self._become_paused(True)

        run.time_next = self.run_time_next
        self.on_machine_run_complete()
        self.machine_run = None
        return res

    #
    # Variables / methods related to pausing.
    #

    # Internal method which actually puts the machine in a paused or
    # resumed state. Not for external use, and subclasses should be
    # careful when they use this - it's preferred if they didn't at all!
    def _become_paused(self, paused, set_state=True):
        if self.machine_state != self.PAUSED and paused:
            assert self.paused, (
                'cannot set machine into paused state without pause flag '
                'also being set'
            )
            if set_state:
                self.machine_state = self.PAUSED
            self.pause_time = self.now()
            self.on_machine_pause()
        elif self.machine_state == self.PAUSED and not paused:
            assert not self.paused, (
                'cannot set machine into resumed state while pause flag '
                'is still set'
            )
            if set_state:
                self.machine_state = self.RUNNING
            self.pause_time = None

            # This might be a property which is automatically calculated,
            # so we don't care too much if we can't reset it.
            try:
                self.pause_until = None
            except AttributeError:
                pass

            self.on_machine_resume()

    #
    # The following methods either need to be overridden by subclasses,
    # or are specifically provided for the use of subclasses to hook
    # into their logic.
    #
    # In most cases, the on_ methods are safe to override completely
    # (without calling the subclass definition). In most cases however,
    # you are encouraged to call the original subclass definition.
    #
    def execute(self):
        """Main block of code to execute in a run. Subclasses must define
        this."""
        raise NotImplementedError

    def on_machine_error(self, exception):
        """Hook provided to allow subclasses to react when an error
        occurs outside of the execute block.

        Default implementation will log via cherrypy.log."""
        cherrypy.log(traceback=True)

    def on_machine_fail(self, exception):
        """Hook provided to allow subclasses to react when a fatal
        error has caused the machine service to halt.

        Default implementation will call on_error."""
        cherrypy.log.error('{0.machine_name} failed.'.format(self))
        self.on_machine_error(exception)

    def on_machine_run_complete(self):
        """Hook provided to allow subclasses to perform a particular
        act when an execution run has finished.

        The main use cases for overriding this will be:

          1) When you want to perform an action after the run has
             completed, but you need to know when the next run time is
             scheduled for (if you don't, you can just do what you need
             at the end of "execute").

          2) When you want to add additional information to a run object
             - although you can do this during the execute loop by
             accessing the machine_run attribute.

        The machine_run attribute will still link to the run object to
        allow it to be queried and modified.
        """
        pass

    def on_machine_pause(self):
        """Hook provided to allow subclasses to react when the machine
        puts itself into a paused state; if an external caller requests
        the machine to pause, this hook is invoked when the machine
        itself actually enters into the paused state, and not at the point
        that a pause "request" is made (there may be a delay between the two
        events).

        Default implementation will log a message about going into a
        paused state via cherrypy.log.
        """
        cherrypy.log('{0.machine_name} paused.'.format(self))

    def on_machine_resume(self):
        """Hook provided to allow subclasses to react when the machine
        resumes itself from a paused state; if an external caller requests
        the machine to resume, this hook is invoked when the machine
        itself actually has resumed running, and not at the point that a
        resume "request" is made (there may be a delay between the two
        events).

        Default implementation will log a message about resuming
        execution via cherrypy.log.
        """
        cherrypy.log('{0.machine_name} resumed.'.format(self))

    def on_machine_stopping(self):
        '''Hook provided to allow subclasses to react when the machine
        is being terminated - this is primarily to allow winding down
        of open resources.'''
        pass

    def on_machine_pause_elapsed(self):
        '''Hook provided to allow subclasses to react when the machine
        has been paused longer than the value on pause_until. Subclasses
        need to either resume the service or extend the value of
        pause_until. Failure to do either will result in the machine
        being effectively stuck in a loop which consumes as much CPU
        as it can get.'''
        pass


    def on_machine_pause_due_to_error(self, error):
        """Hook to allow subclasses to react on the event that the
        machine is going to move into a paused state due to an error
        occurring.

        Subclasses can override this method, but must call the subclass
        definition of it. Prior to the call, the machine will still be
        in a running state - after it, the machine will be internally
        set to paused."""
        self._become_paused(True)


#
# We build the extensions related to pausing into this subclass.
#
# noinspection PyAbstractClass
class Machine(BoneMachine):

    """A CherryPy-integrated task which runs continuously in its own thread.

    Generally, you will want to subclass this and override the 'execute'
    method to perform the same work on a recurring basis:

    >>> class MyMachine(Machine):
    ...    def execute(self):
    ...        foo()
    >>> m = MyMachine('test')
    >>> m.subscribe()

    There are a lot of exposed variables and hooks available to customise
    some behaviour.
    """

    # Last time we generated an alert.
    pause_alert_last = None

    # How long we wait after being initially paused to generate a
    # status update - defaults to 5 minutes.
    pause_alert_initial_threshold = 300

    # How long we wait to repeat status updates after the last status
    # update was sent out (whie we're paused). Defaults to every 30 mins.
    pause_alert_further_threshold = 1800

    # The number of pause alerts we've generated while we've been
    # currently paused.
    pause_alert_count = None

    # The username of who has put the machine into pause mode. If None,
    # then it's presumed the service itself has done this.
    pause_actor = None

    # Text description indicating why the service has been paused.
    pause_reason = None

    # Shall we start paused?
    pause_on_start = False

    _pause_until = None

    @property
    def pause_until(self):
        """Override pause_until - it should base itself on the next time
        we are due to generate an alert."""

        # Allow the pause_until flag to still be set manually if
        # subclasses want to do it. At the same time, let's return the
        # earliest time out of the next due alert and the manually set
        # pause time.
        pause_times = [self.pause_alert_next]
        if self._pause_until is not None:
            pause_times.append(self._pause_until)
        return min(pause_times)

    @pause_until.setter
    def pause_until(self, value):

        # Setting a new time to pause until will mean we may need to
        # wake up earlier than we intended - so we must interrupt the
        # main thread to take that into account.
        self._pause_until = value
        self.interrupt()

    @property
    def pause_alert_next(self):
        """The next time a pause alert is due to be generated - this
        is calculated automatically based on the time of the previous
        alert (if any)."""
        if self.pause_time is None:
            return None

        # Not generated an alert yet.
        if self.pause_alert_last is None:
            start = self.pause_time
            delta = self.pause_alert_initial_threshold

        # Have generated a single alert.
        elif self.pause_alert_count == 1:

            # The first reminder alert needs to be relative to the
            # original pause time, not the last reminder.
            start = self.pause_time
            delta = self.pause_alert_further_threshold

        # Have generated multiple alerts.
        else:
            start = self.pause_alert_last
            delta = self.pause_alert_further_threshold

        return start + datetime.timedelta(seconds=delta)

    # Override start to handle the pause_on_start flag.
    def start(self):
        """Start processing in a new Thread."""

        # Means we're about to start the machine...
        if self.machine_thread is None and self.pause_on_start:
            self.pause_for_reason(None, 'pause_on_start flag was set.')
        super(Machine, self).start()

    # If something goes wrong, notify the service status list.
    def on_machine_fail(self, exception):
        super(Machine, self).on_machine_fail(exception)

        # Turn off indication that we are paused, so we don't confuse
        # notify_status_via_email.
        self.paused = False
        self.pause_time = self.pause_actor = self.pause_reason = None
        self.notify_status_via_email()

    # Record the reason why we're pausing and generate an immediate
    # e-mail.
    def on_machine_pause_due_to_error(self, error):
        self.pause_for_reason(None, 'automatic pause due to error occurring.')
        super(Machine, self).on_machine_pause_due_to_error(error)
        self.notify_status_via_email()

    # If we're paused longer than intended, then generate a status
    # update and refresh the recorded time of the last alert.
    def on_machine_pause_elapsed(self):
        """Subclasses should override on_machine_pause_until_elapsed rather
           than this method."""
        now = self.now()

        # Subclasses may set pause_until and want to know explicitly when
        # that moment has elapsed, so we provide a subclass hook for it.
        if self._pause_until and now > self._pause_until:
            self.on_machine_pause_until_elapsed()

            # If the subclass unpaused itself, then don't bother generating
            # alerts - just come out of this method.
            if not self.paused:
                return

        if now > self.pause_alert_next:
            self.notify_status_via_email()

    def on_machine_pause_until_elapsed(self):
        pass

    # Log to the activity log on pause.
    def on_machine_pause(self):
        super(Machine, self).on_machine_pause()
        self.pause_alert_count = 0

    # Log to the activity log on resume.
    def on_machine_resume(self):
        super(Machine, self).on_machine_resume()

        # If we generated an alert about being paused, we should inform
        # everyone that we're now resumed.
        if self.pause_alert_last:
            self.notify_status_via_email()
            self.pause_alert_last = None

        # Reset these values.
        self.pause_actor = self.pause_reason = None
        self.pause_alert_count = None

    # If we became paused during an execute invocation, notify people
    # immediately.
    def on_machine_run_complete(self):
        if self.machine_run.pause_flag_set:
            self.notify_status_via_email()

    @property
    def pause_actor_text(self):
        return self.pause_actor or 'itself'

    @property
    def pause_time_text(self):
        pause_secs = max((self.now() - self.pause_time).seconds, 1)
        mins, secs = divmod(pause_secs, 60)
        hours, mins = divmod(mins, 60)

        hours_pl = 's' if hours > 1 else ''
        mins_pl = 's' if mins > 1 else ''
        secs_pl = 's' if secs > 1 else ''

        parts = []
        if hours:
            parts.append('{hours} hour{hours_pl}')
        if mins:
            parts.append('{mins} minute{mins_pl}')
        if secs:
            parts.append('{secs} second{secs_pl}')

        if len(parts) > 2:
            parts[:-1] = [', '.join(parts[:-1])]

        msg = ' and '.join(parts)
        return msg.format(**vars())

    def pause_for_reason(self, actor, reason):
        """Tells the machine to pause, but indicates who is requesting
        it and why.

        actor should be a dictionary of the form:
          {'buserid': buserid_int, 'username': username_str}

        This is usually available in a CherryPy request as:
          cherrypy.request.buser['username']

        If actor is None, this indicates the machine itself is doing
        this.

        reason should be a string."""
        if actor is None:
            actor = dict(username=None, buserid=None)

        self.paused = True
        self.pause_actor = actor['username']
        self.pause_reason = reason

        msg_actor = (
            '{0.machine_name} set to pause by {0.pause_actor_text} - '
            '{0.pause_reason}'
        )
        msg_no_actor = '{0.machine_name} set to pause - {0.pause_reason}'

        cherrypy.log(msg_actor.format(self))

    def resume_by(self, actor):
        """Tells the machine to resume, and indicates who is requesting
        it.

        actor should be a dictionary of the form:
          {'buserid': buserid_int, 'username': username_str}

        This is usually available in a CherryPy request as:
          cherrypy.request.buser['username']

        If actor is None, this indicates the machine itself is doing
        this."""

        # We set username to be an empty string, so that we are
        # indicating that the machine resumed itself - if we set it to
        # None, then that indicates we haven't recorded which user
        # performed the resume action.
        if actor is None:
            actor = dict(username='', buserid=None)

        # Setting the pause actor but with no reason is a way of
        # recording who resumed the service.
        self.paused = False
        self.pause_actor = actor['username']
        self.pause_reason = None

        msg_actor = '{0.machine_name} set to resume by {1}.'
        msg_no_actor = '{0.machine_name} set to resume.'

        cherrypy.log(msg_actor.format(self, actor['username']))

    def notify_status_via_email(self, message=None):
        self.pause_alert_last = self.now()
        self.pause_alert_count += 1

    def subscribe(self):
        e = cherrypy.engine
        e.subscribe('start', self.start)
        e.subscribe('stop', self.stop)

    def unsubscribe(self):
        e = cherrypy.engine
        e.unsubscribe('start', self.start)
        e.unsubscribe('stop', self.stop)

    def override_signal_handler(self):
        """Integrates with CherryPy's signal handling mechanism so that
        it will only shut down the web service once the main thread
        itself has terminated.

        Returns true if it was modified successfully.
        """
        try:
            handler = cherrypy.engine.signal_handler
        except AttributeError:
            return False

        old_sigterm_handler = handler.handlers['SIGTERM']

        def delayed_stop():
            our_thread = self.machine_thread
            self.stop() # This will clear the reference to the machine thread.

            # We don't want multiple signals to cause this service
            # to halt. We trust that after the main thread has
            # finished, we will pass on the signal. We won't allow
            # any other signals to make their way through.
            handler.handlers['SIGTERM'] = lambda: None

            # Just in case we're triggered more than once, we protect
            # against the possibility that we receive the signal more
            # than once.
            if our_thread:
                cherrypy.log(
                    'Waiting for thread "%s" to terminate before shutting '
                    'down.' % our_thread.name
                )
                our_thread.join()
                cherrypy.log('Thread "%s" terminated.' % our_thread.name)

            # Shut down everything else.
            old_sigterm_handler()

        handler.handlers['SIGTERM'] = delayed_stop
        handler.subscribe()
        return True

    def status(self):
        '''Returns a dictionary describing the current state of the
        machine. Intended to be called from any thread. Subclasses are
        encouraged to override the definition to include additional data.'''
        res = dict(
            state=self.machine_state,
            times=dict(
                start=self.run_time_start,
                next=self.run_time_next,
            )
        )
        if self.run_time_end is not None:
            res['times']['end'] = self.run_time_end

        if self.machine_up_since is not None:
            res['uptime'] = (self.now() - self.machine_up_since).seconds

        res['active'] = self.machine_active
        return res
