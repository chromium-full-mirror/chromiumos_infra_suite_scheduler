# Setup

1. Put your Google gCloud SDK to `~/google-cloud-sdk`.

   [SDK download page](https://cloud.google.com/sdk/docs/)

2. Install App Engine SDK to `~/google-cloud-sdk`:

        ~/google-cloud-sdk/bin/gcloud components install app-engine-python

3. Run `python setup_environment.py` to download third-party libraries and credentials.

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
        project. Please contact @xixuan to whitelist your ldap.

# How to test:

1. Presubmit will kick off sanity test for verifying suite_scheduler.ini:

        python runner.py --test_type sanity

2. Run unittest:

        python runner.py' or 'python runner.py --test_type unittest

3. Run integration test:

        python runner.py --test_type integration

4. Run tests with debug mode:

        python runner.py --debug

5. Run suite scheduler v2 in local development server:

   If you want to verify any APIs locally, you can run suite scheduler v2 in
   local development server
   (https://cloud.google.com/appengine/docs/standard/python/tools/using-local-server):


      Assuming you already get credentials/cloud_sql_credentials.txt by
      running 'setup_environment.py':

          CONNECTION_NAME = connection_name in [CIDB]
          USER = user in [CIDB]

      a. Test locally on your workstation to make sure you're whitelisted:

          /google/data/ro/projects/speckle/mysql -S /cloudsql/CONNECTION_NAME -u USER || echo "You may need to run prodaccess"

      b. Start dev_appserver.py in a window:

          dev_appserver.py app.yaml --port=8888 --admin_port=8001 --log_level=debug


      c. Start the cloud_sql_proxy in a new window:

          ./cloud_sql_proxy -dir=/cloudsql -instances=CONNECTION_NAME &
          -credential_file=./credentials/suite-scheduler_client_secret_service_account.json &

      d. Test it:

          curl 'http://localhost:8888/cron/trigger_event', or open it in chrome.

    Please note that once a dev_appserver is started, it simulates data_store &
    task_queue, which causes:

      a. The datastore doesn't contain any previous cron run's information, so
      the first round of cron/trigger_event won't trigger any event.

      b. The task queue is newly created with 0 tasks in it unless
      cron/trigger_event adds tasks in it. Dev_appserver restart will cause the
      local task queue to get purged.
