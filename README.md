# Suite-Scheduler README

* [Developer Setup](#developer-setup)
* [Testing your changes](#testing)
* [Making configuration changes](#modify-config)
* [Running an instance locally](#run-local)
* [Releasing to production](#release)


## Developer Setup {#developer-setup}

### SDK

suite-scheduler is an AppEngine Standard Python Environment V1 application. You
need the Google Cloud SDK's AppEngine Python component to develop and deploy
this application:

* Install Google Cloud SDK:
  * Follow the [instructions][install-sdk] to install the Python App Engine component.
* Log in to gcloud: `gcloud auth login <username>@google.com`

[install-sdk]: https://cloud.google.com/sdk/docs#install_the_latest_cloud_sdk_version

* Install App Engine Python extensions
  * `gcloud components install app-engine-python`
  * `gcloud components install app-engine-python-extras`

### Developer environment

Suite-scheduler development must be done in the standard [Chrome OS source
checkout][cros-checkout] but entirely outside the Chrome OS chroot environment.

suite-scheduler uses [infra_virtualenv] to provide a stable environment for
development and release.

First, make sure you
[install](https://virtualenv.pypa.io/en/latest/installation.html) `virtualenv`
with version at least 20.0.

Then, to (re)initialize developer environment, run
```
  bin/setup_environment
```

For testing changes beyond to the `configs/` directory, and for deploying
suite-scheduler, you must also obtain certain service credentials used by
suite-scheduler.
```
  bin/setup_environment --load-creds
```

If you get [failures when trying to download credentials][creds-fail],

* Double check you're logged into the Google Cloud SDK by running
  `gcloud auth list`.
* Contact Test Platform team or one of the [OWNERS] to be whitelisted.

[cros-checkout]: https://chromium.googlesource.com/chromiumos/docs/+/master/developer_guide.md#Get-the-Source
[infra_virtualenv]: https://chromium.googlesource.com/chromiumos/infra_virtualenv/+/refs/heads/master/README.md
[creds-fail]: https://crbug.com/792690
[OWNERS]: https://chromium.googlesource.com/chromiumos/infra/suite_scheduler/+/refs/heads/master/OWNERS


## Testing your changes {#testing}

Changes to `configs/*` directory can be tested via sanity tests alone:
```
  bin/run_sanity_tests
  bin/run_sanity_tests --debug  # More verbose
```

Other changes must be validated with the full test suite:
```
  bin/run_tests
  bin/run_tests --debug  # More verbose
```

These tests include some integration tests that can take over 5 minutes to run.

**
WARNING: suite-scheduler unittests do not currently run in presubmit. You
MUST ensure that unit-tests pass locally for your change.
**


## Making configuration changes {#modify-config}

* Add or update your job configuration in `configs/suite_scheduler.ini`.
* Update `configs/lab_config.ini`, if the suite test relies on new board or
  model. Note, suite scheduler does not automatically catch the new boards or
  models added to the lab.
* **[Test your changes](#testing)**.
* Submit the change and ping/file bug to infra team. Test platform deputy will
   rollout your change to the production. Once this is done, you may find the
   scheduling status of the new suite via our [dashboard](go/ctp-).


## Running an instance locally {#run-local}

If you want to verify any APIs locally, you can run suite scheduler v2 as a
local development server
(https://cloud.google.com/appengine/docs/standard/python/tools/using-local-server):

a. Finally, start dev_appserver.py in a window:

        dev_appserver.py app.yaml \
        --port=8888 \
        --admin_port=8001 \
        --log_level=debug

b. Test it:

        curl 'http://localhost:8888/cron/trigger_event', or open it in chrome.

Please note that once a dev_appserver is started, it simulates data_store &
task_queue, which means:

a. The datastore doesn't contain any previous cron run's information, so
the first round of cron/trigger_event won't trigger any event.

b. The task queue is newly created with 0 tasks in it unless
cron/trigger_event adds tasks in it. Dev_appserver restart will cause the
local task queue to get purged.


## Releasing to production {#release}

There are two instances of suite-scheduler:

* [Staging](https://pantheon.corp.google.com/appengine?organizationId=433637338589&project=google.com:suite-scheduler-staging&serviceId=default)
* [Prod](https://pantheon.corp.google.com/appengine?authuser=0&project=google.com:suite-scheduler&serviceId=default)

All releases must follow the following process:
* Release to staging instance
  ```
    bin/deploy
  ```
* Go the to [cron page for the staging instance][staging-cron] and manually
  trigger `cron/test_push`. Verify there are no obvious failures by looking at
  service logs.
* Note the [currently deployed prod version][current-prod-version], in case
  you need to rollback.
* Release to prod instance
  ```
    bin/deploy -p
  ```

Run `bin/deploy -h` for more usage information.

If there are issues discovered in prod after release, rollback to the previous
version.
```
  gcloud app versions migrate --project=google.com:suite-scheduler ${VERSION}
```

[staging-cron]: https://pantheon.corp.google.com/appengine/cronjobs?organizationId=433637338589&project=google.com:suite-scheduler-staging
[current-prod-version]: https://pantheon.corp.google.com/appengine/versions?authuser=0&project=google.com:suite-scheduler&serviceId=default
