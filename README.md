# Setup

1. Put your Google gCloud SDK in `~/google-cloud-sdk`.

   [SDK download page](https://cloud.google.com/sdk/docs/)

2. Install App Engine SDK in `~/google-cloud-sdk`:

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

5. Run suite scheduler v2 as a local development server:

   If you want to verify any APIs locally, you can run suite scheduler v2 as a
   local development server
   (https://cloud.google.com/appengine/docs/standard/python/tools/using-local-server):


      Assuming you already got credentials/cloud_sql_credentials.txt by
      running 'setup_environment.py', set up some variables based on the
      database instance you want to connect to:

          # Set up CONNECTION_NAME based on the cloudsql project/instance
          # name.  For more details, see:
          # https://docs.google.com/document/d/1e_3mcsxdRKECYuYaIfpHcqf_TjnxxfHDKtidn900dEg/edit
          CONNECTION_NAME='cosmic-strategy-646:us-central1:cidb-gen2-replica2'

          # Set up USER based on the user you want to log in.  If you use
          # readonly_nopw, grab the password from (as of April, 2018):
          # https://valentine.corp.google.com/#/show/1493156766394660?tab=metadata
          USER='readonly_nopw' # [CIDB username]

      a. Test locally on your workstation to make sure you're whitelisted:

          /google/data/ro/projects/speckle/mysql \
              -S /cloudsql/${CONNECTION_NAME} \
              -u ${USER} \
              || echo "You may need to run prodaccess"

      b. Start the cloud_sql_proxy in a new window to let your service talk
         to cloud sql.  Note that cloud_sql_proxy needs to be downloaded from
         Google's public cloud website:
         https://cloud.google.com/sql/docs/mysql/sql-proxy

          # Create the /cloudsql directory, since the suite scheduler assumes
          # that this is where to find it's socket.
          sudo mkdir /cloudsql
          sudo chmod 1777 /cloudsql

          # Start the cloud sql proxy.
          ./cloud_sql_proxy \
              -dir=/cloudsql \
              -instances=${CONNECTION_NAME} \
              -credential_file=./credentials/suite-scheduler_client_secret_service_account.json &

      c. Finally, start dev_appserver.py in a window:

          dev_appserver.py app.yaml \
              --port=8888 \
              --admin_port=8001 \
              --log_level=debug

      d. Test it:

          curl 'http://localhost:8888/cron/trigger_event', or open it in chrome.

    Please note that once a dev_appserver is started, it simulates data_store &
    task_queue, which means:

      a. The datastore doesn't contain any previous cron run's information, so
      the first round of cron/trigger_event won't trigger any event.

      b. The task queue is newly created with 0 tasks in it unless
      cron/trigger_event adds tasks in it. Dev_appserver restart will cause the
      local task queue to get purged.

