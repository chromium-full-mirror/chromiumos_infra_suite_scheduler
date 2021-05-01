# Suite-Scheduler README

* [Developer Setup](#developer-setup)
* [Testing your changes](#testing)
* [Making configuration changes](#modify-config)
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
* Contact Test Platform team or one of the [OWNERS] to be allowlisted.

[cros-checkout]: https://chromium.googlesource.com/chromiumos/docs/+/master/developer_guide.md#Get-the-Source
[infra_virtualenv]: https://chromium.googlesource.com/chromiumos/infra_virtualenv/+/refs/heads/master/README.md
[creds-fail]: https://crbug.com/792690
[OWNERS]: https://chromium.googlesource.com/chromiumos/infra/suite_scheduler/+/refs/heads/master/OWNERS


## Testing your changes {#testing}

Changes must be validated with the full test suite:
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

Changes to suite-scheduler configs are made in config-internal, as of 2020. Detailed instructions on adding/editing config files can be found at [go/ss-configs](http://go/ss-configs).


## Releasing to production {#release}

There are two instances of suite-scheduler:

* [Staging](https://pantheon.corp.google.com/appengine?organizationId=433637338589&project=google.com:suite-scheduler-staging&serviceId=default)
* [Prod](https://pantheon.corp.google.com/appengine?authuser=0&project=google.com:suite-scheduler&serviceId=default)

Detailed deployment instructions can be found at [go/suite-scheduler#deployment](go/suite-scheduler#deployment).
