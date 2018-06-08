0.2.4
=====

* When we receive a SystemExit or KeyboardInterrupt, set the machine to stopping before reraising
  the exception - this will prevent errors being reported where the machine is still attempting
  to execute even though the service is shutting down.

0.2.3
=====

* Fixed bug in scheduling logic for services which don't run on a scheduled repeated basis.

0.2
===

* Improved documentation.
* Signal handler to handle shutdowns now works even when the machine thread has stopped (or failed).
* Remove on_machine_postexecute hook in favour of encouraging use of on_machine_run_complete.
* Dropped wait_on_error_default flag.

0.1.1
=====

Initial version.
