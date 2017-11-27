0.2
===

* Improved documentation.
* Signal handler to handle shutdowns now works even when the machine thread has stopped (or failed).
* Remove on_machine_postexecute hook in favour of encouraging use of on_machine_run_complete.
* Dropped wait_on_error_default flag.

0.1.1
=====

Initial version.
