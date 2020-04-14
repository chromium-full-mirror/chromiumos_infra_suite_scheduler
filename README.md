# Setup

Due to https://crbug.com/792690, this must be run outside the chroot.

1. Install Google Cloud SDK:

    1. Follow the [instructions](https://cloud.google.com/sdk/docs/quickstart-debian-ubuntu).
    2. Install the Python App Engine component:

            sudo apt-get install google-cloud-sdk-app-engine-python

2. Log in to gcloud: `gcloud auth login LDAP@google.com`
3. Install `pip`:

        sudo apt-get install python-pip

4. If you only modify the files in `configs/`, run `python setup_environment.py`
   to download third-party libraries. Otherwise, load the full dependencies:

        python setup_environment.py --load_infra_libs --load_cred

# Known Issues

1. [Failed to install third-packages in requirement.txt](https://crbug.com/792690):

   Workround: Run `pip install -t lib -r requirements.txt` locally on your
   workstation to verify whether it could work.

2. [Failed to download credentials from 'gs://suite-scheduler.google.com.a.appspot.com/credentials/'](https://crbug.com/792690):

   Workround: Run `gsutil ls gs://suite-scheduler.google.com.a.appspot.com/credentials/`
   locally on your workstation to verify whether you can fetch credentials with
   gsutil.

   If there's any auth issue, it may be because

     a. You're not using your corp account to login gcloud. Please run
        `gcloud auth list` to check what's the used account for
        gcloud.

     b. Your corp account is not whitelisted by suite-scheduler
        project. Please contact @lxn to whitelist your ldap.

# How to test:

1. Run sanity test for config changes:

        python runner.py --test_type sanity

2. Run unittest and integration for any changes in production code:

        python runner.py --test_type unittest
        python runner.py --test_type integration

3. Run tests with debug mode:

        python runner.py --debug

4. Run suite scheduler v2 as a local development server:

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

# How to add or update your job to schedule a suite test:

1. Add or update your job configuration in `configs/suite_scheduler.ini`.

2. Update `configs/lab_config.ini`, if the suite test relies on new board or
   model. Note, suite scheduler does not automatically catch the new boards or
   models added to the lab.

3. Run `python runner.py --test_type sanity` to ensure config is eligible.

4. Submit the change and ping/file bug to infra team. Test platform deputy will
   rollout your change to the production. Once this is done, you may find the
   scheduling status of the new suite via our [dashboard](go/ctp-).
