# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tasks triggered by suite scheduler."""
# pylint: disable=g-bad-import-order
# pylint: disable=dangerous-default-value

from distutils import version
import MySQLdb
import logging

import build_lib
import task_executor
import tot_manager

# The max lifetime of a suite scheduled by suite scheduler
_JOB_MAX_RUNTIME_MINS_DEFAULT = 72 * 60

# One kind of formats for RO firmware spec.
_RELEASE_RO_FIRMWARE_SPEC = 'released_ro_'


class SchedulingError(Exception):
  """Raised to indicate a failure in scheduling a task."""


class Task(object):
  """Represents an entry from the suite_scheduler config file.

  Each entry from the suite_scheduler config file maps one-to-one to a
  Task. Each instance has enough information to schedule itself.
  """

  def __init__(self, task_info, board_family_config={}, tot=None):
    """Initialize a task instance.

    Args:
      task_info: a config_reader.TaskInfo object, which includes:
          name, name of this task, e.g. 'NightlyPower'
          suite, the name of the suite to run, e.g. 'graphics_per-day'
          branch_specs, a pre-vetted iterable of branch specifiers,
            e.g. ['>=R18', 'factory']
          pool, the pool of machines to schedule tasks. Default is None.
          num, the number of devices to shard the test suite. It could
            be an Integer or None. By default it's None.
          board_families, a common separated list of board family to run this
            task on. Boards belong to one of the board family in this list
            would be added to task_info.boards.
          boards, a comma separated list of boards to run this task on. Default
            is None, which allows this task to run on all boards. If same board
            is specified in 'boards' and 'exclude_boards', we exclude this
            board.
          exclude_board_families, a common separated list of board family not to
            run task on. Boards belong to one of the board family in this list
            would be added to task_info.exclude_boards.
          exclude_boards, a comma separated list of boards not to run this task
            on. Default is None, which allows this task to run on all boards.
            If same board is specified in 'boards' and 'exclude_boards', we
            exclude this board.
          models, a comma separated list of models to run this task on. Default
            is None, which allows this task to run on all models. If same model
            is specified in 'models' and 'exclude_models', we exclude this
            model.
          exclude_models, a comma separated list of models not to run this task
            on. Default is None, which allows this task to run on all models.
          priority, the string name of a priority from constants.Priorities.
          timeout, the max lifetime of the suite in hours.
          cros_build_spec, spec used to determine the ChromeOS build to test
            with a firmware build, e.g., tot, R41 etc.
          firmware_rw_build_spec, spec used to determine the firmware RW build
            test with a ChromeOS build.
          firmware_ro_build_spec, spec used to determine the firmware RO build
            test with a ChromeOS build.
          test_source, the source of test code when firmware will be updated in
            the test. The value can be 'firmware_rw', 'firmware_ro' or 'cros'.
          job_retry, set to True to enable job-level retry. Default is False.
          no_delay, set to True to raise the priority of this task in task.
          force, set to True to schedule this suite no matter whether there's
            duplicate jobs before.
          queue, so the suite jobs can start running tests with no waiting.
          hour, an integer specifying the hour that a nightly run should be
            triggered, default is set to 21.
          day, an integer specifying the day of a week that a weekly run should
            be triggered, default is set to 5 (Saturday).
          os_type, type of OS, e.g., cros, brillo, android. Default is cros.
            The argument is required for android/brillo builds.
          launch_control_branches, comma separated string of launch control
            branches. The argument is required and only applicable for
            android/brillo builds.
          launch_control_targets, comma separated string of build targets for
            launch control builds. The argument is required and only
            applicable for android/brillo builds.
          testbed_dut_count, number of duts to test when using a testbed.
      board_family_config: A board family dictionary mapping board_family name
        to its corresponding boards.
      tot: The tot manager for checking ToT. If it's None, a new tot_manager
        instance will be initialized.
    """
    # Indicate whether there're suites get pushed into taskqueue for this task.
    self.is_pushed = False

    self.name = task_info.name
    self.suite = task_info.suite
    self.branch_specs = task_info.branch_specs
    self.pool = task_info.pool
    self.num = task_info.num
    self.priority = task_info.priority
    self.timeout = task_info.timeout
    self.cros_build_spec = task_info.cros_build_spec
    self.firmware_rw_build_spec = task_info.firmware_rw_build_spec
    self.firmware_ro_build_spec = task_info.firmware_ro_build_spec
    self.test_source = task_info.test_source
    self.job_retry = task_info.job_retry
    self.no_delay = task_info.no_delay
    self.force = task_info.force
    self.os_type = task_info.os_type
    self.testbed_dut_count = task_info.testbed_dut_count
    self.hour = task_info.hour
    self.day = task_info.day
    self.only_hwtest_sanity_required = task_info.only_hwtest_sanity_required

    if task_info.lc_branches:
      self.launch_control_branches = [
          t.strip() for t in task_info.lc_branches.split(',')]
    else:
      self.launch_control_branches = []

    if task_info.lc_targets:
      self.launch_control_targets = [
          t.strip() for t in task_info.lc_targets.split(',')]
    else:
      self.launch_control_targets = []

    if task_info.boards:
      self.boards = [t.strip() for t in task_info.boards.split(',')]
    else:
      self.boards = []

    if task_info.exclude_boards:
      self.exclude_boards = [
          t.strip() for t in task_info.exclude_boards.split(',')]
    else:
      self.exclude_boards = []

    if task_info.models:
      self.models = [t.strip() for t in task_info.models.split(',')]
    else:
      self.models = []

    if task_info.exclude_models:
      self.exclude_models = [
          t.strip() for t in task_info.exclude_models.split(',')]
    else:
      self.exclude_models = []

    if task_info.board_families:
      # Finetune the allowed boards list with board_families & boards.
      families = [family.strip()
                  for family in task_info.board_families.split(',')]
      for family in families:
        self.boards += board_family_config.get(family, [])

    if task_info.exclude_board_families:
      # Finetune the disallowed boards list with exclude_board_families
      # & exclude_boards.
      families = [family.strip()
                  for family in task_info.exclude_board_families.split(',')]
      for family in families:
        self.exclude_boards += board_family_config.get(family, [])

    if tot is None:
      self.tot_manager = tot_manager.TotMilestoneManager()
    else:
      self.tot_manager = tot

    self._set_spec_compare_info()

  def schedule(self, launch_control_builds, cros_builds_tuple, lab_config,
               db_client):
    """Schedule the task by its settings.

    Args:
      launch_control_builds: the build dict for Android boards, see
        return value of |get_launch_control_builds|.
      cros_builds_tuple: the two-tuple of build dicts for ChromeOS boards,
        see return value of |get_cros_builds|.
      lab_config: a config.LabConfig object, to read lab config file.
      db_client: a cloud_sql_client.CIDBClient object to connect to cidb.

    Raises:
      SchedulingError: if tasks that should be scheduled fail to schedule.

    Returns:
      A boolean indicator; true if there were any suites related to this
        task which got pushed into the suites queue.
    """
    assert lab_config is not None
    self.is_pushed = False

    branch_builds, relaxed_builds = cros_builds_tuple
    builds_dict = branch_builds
    if self.only_hwtest_sanity_required:
      builds_dict = relaxed_builds

    logging.info('######## Scheduling task %s ########', self.name)
    if self.os_type == build_lib.OS_TYPE_CROS:
      if not builds_dict:
        logging.info('No CrOS build to run, skip running.')
      else:
        self._schedule_cros_builds(builds_dict, lab_config, db_client)
    else:
      if not launch_control_builds:
        logging.info('No Android build to run, skip running.')
      else:
        self._schedule_launch_control_builds(launch_control_builds)

    return self.is_pushed

  def _set_spec_compare_info(self):
    """Set branch spec compare info for task for further check."""
    self._bare_branches = []
    self._version_equal_constraint = False
    self._version_gte_constraint = False
    self._version_lte_constraint = False

    if not self.branch_specs:
      # Any milestone is OK.
      self._numeric_constraint = version.LooseVersion('0')
    else:
      self._numeric_constraint = None
      for spec in self.branch_specs:
        if 'tot' in spec.lower():
          # Convert spec >=tot-1 to >=RXX.
          tot_str = spec[spec.index('tot'):]
          spec = spec.replace(
              tot_str, self.tot_manager.convert_tot_spec(tot_str))

        if spec.startswith('>='):
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('>=R'))
          self._version_gte_constraint = True
        elif spec.startswith('<='):
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('<=R'))
          self._version_lte_constraint = True
        elif spec.startswith('=='):
          self._version_equal_constraint = True
          self._numeric_constraint = version.LooseVersion(
              spec.lstrip('==R'))
        else:
          self._bare_branches.append(spec)

  def _fits_spec(self, branch):
    """Check if a branch is deemed OK by this task's branch specs.

    Will return whether a branch 'fits' the specifications stored in this task.

    Examples:
    Assuming tot=R40
    t = Task('Name', 'suite', ['factory', '>=tot-1'])
    t._fits_spec('factory')  # True
    t._fits_spec('40')  # True
    t._fits_spec('38')  # False
    t._fits_spec('firmware')  # False

    Args:
      branch: the branch to check.

    Returns:
      True if branch 'fits' with stored specs, False otherwise.
    """
    if branch in build_lib.BARE_BRANCHES:
      return branch in self._bare_branches

    if self._numeric_constraint:
      if self._version_equal_constraint:
        return version.LooseVersion(branch) == self._numeric_constraint
      elif self._version_gte_constraint:
        return version.LooseVersion(branch) >= self._numeric_constraint
      elif self._version_lte_constraint:
        return version.LooseVersion(branch) <= self._numeric_constraint
      else:
        return version.LooseVersion(branch) >= self._numeric_constraint
    else:
      return False

  def _get_latest_firmware_build_from_db(self, spec, board, db_client):
    """Get the latest firmware build from CIDB database.

    Args:
      spec: a string build spec for RO or RW firmware, eg. firmware,
        cros. For RO firmware, the value can also be released_ro_X.
      board: the board against which this task will run suite job.
      db_client: a cloud_sql_client.CIDBClient object to connect to cidb.

    Returns:
      the latest firmware build.

    Raises:
      MySQLdb.OperationalError: if connection operations are not valid.
    """
    build_type = 'release' if spec == 'cros' else spec
    # TODO(xixuan): not all firmware are saved in cidb.
    build = db_client.get_latest_passed_builds('%s-%s' % (board, build_type))

    if build is None:
      return None
    else:
      latest_build = str(build_lib.CrOSBuild(
          board, build_type, build.milestone, build.platform))
      logging.debug('latest firmware build for %s-%s: %s', board,
                    build_type, latest_build)
      return latest_build

  def _get_latest_firmware_build_from_lab_config(self, spec, board,
                                                 lab_config):
    """Get latest firmware from lab config file.

    Args:
      spec: a string build spec for RO or RW firmware, eg. firmware,
        cros. For RO firmware, the value can also be released_ro_X.
      board: a string board against which this task will run suite job.
      lab_config: a config.LabConfig object, to read lab config file.

    Returns:
      A string latest firmware build.

    Raises:
      ValueError: if no firmware build list is found in lab config file.
    """
    index = int(spec[len(_RELEASE_RO_FIRMWARE_SPEC):])
    released_ro_builds = lab_config.get_firmware_ro_build_list(
        'RELEASED_RO_BUILDS_%s' % board).split(',')
    if len(released_ro_builds) < index:
      raise ValueError('No %dth ro_builds in the lab_config firmware '
                       'list %r' % (index, released_ro_builds))

    logging.debug('Get ro_build: %s', released_ro_builds[index - 1])
    return released_ro_builds[index - 1]

  def _get_firmware_build(self, spec, board, lab_config, db_client):
    """Get the firmware build name to test with ChromeOS build.

    Args:
      spec: a string build spec for RO or RW firmware, eg. firmware,
        cros. For RO firmware, the value can also be released_ro_X.
      board: a string board against which this task will run suite job.
      lab_config: a config.LabConfig object, to read lab config file.
      db_client: a cloud_sql_client.CIDBClient object to connect to cidb.

    Returns:
      A string firmware build name.

    Raises:
      ValueError: if failing to get firmware from lab config file;
      MySQLdb.OperationalError: if DB connection is not available.
    """
    if not spec or spec == 'stable':
      # TODO(crbug.com/577316): Query stable RO firmware.
      logging.debug('%s RO firmware build is not supported.', spec)
      return None

    try:
      if spec.startswith(_RELEASE_RO_FIRMWARE_SPEC):
        # For RO firmware whose value is released_ro_X, where X is the index of
        # the list defined in lab config file:
        #     CROS/RELEASED_RO_BUILDS_[board].
        # For example, for spec 'released_ro_2', and lab config file
        # CROS/RELEASED_RO_BUILDS_veyron_jerry: build1,build2,
        # return firmware RO build should be 'build2'.
        return self._get_latest_firmware_build_from_lab_config(
            spec, board, lab_config)
      else:
        return self._get_latest_firmware_build_from_db(spec, board, db_client)
    except ValueError as e:
      logging.warning('Failed to get firmware from lab config file'
                      'for spec %s, board %s: %s', spec, board, str(e))
      return None
    except MySQLdb.OperationalError as e:
      logging.warning('Failed to get firmware from cidb for spec %s, '
                      'board %s: %s', spec, board, str(e))
      return None

  def _push_suite(
      self,
      board=None,
      model=None,
      cros_build=None,
      firmware_rw_build=None,
      firmware_ro_build=None,
      test_source_build=None,
      launch_control_build=None,
      run_prod_code=False,
      is_skylab=False):
    """Schedule suite job for the task by pushing suites to SuiteQueue.

    Args:
      board: the board against which this suite job run.
      model: the model name for unibuild.
      cros_build: the CrOS build of this suite job.
      firmware_rw_build: Firmware RW build to run this suite job with.
      firmware_ro_build: Firmware RO build to run this suite job with.
      test_source_build: Test source build, used for server-side
        packaging of this suite job.
      launch_control_build: the launch control build of this suite job.
      run_prod_code: If True, the suite will run the test code that lives
        in prod aka the test code currently on the lab servers. If
        False, the control files and test code for this suite run will
        be retrieved from the build artifacts. Default is False.
      is_skylab: If True, schedule this suite to skylab, otherwise schedule
        it to AFE. Default is False.
    """
    android_build = None
    testbed_build = None

    if self.testbed_dut_count:
      launch_control_build = '%s#%d' % (launch_control_build,
                                        self.testbed_dut_count)
      test_source_build = launch_control_build
      board = '%s-%d' % (board, self.testbed_dut_count)

    if launch_control_build:
      if not self.testbed_dut_count:
        android_build = launch_control_build
      else:
        testbed_build = launch_control_build

    suite_job_parameters = {
        'suite': self.suite,
        'board': board,
        'model': model,
        build_lib.BuildVersionKey.CROS_VERSION: cros_build,
        build_lib.BuildVersionKey.FW_RW_VERSION: firmware_rw_build,
        build_lib.BuildVersionKey.FW_RO_VERSION: firmware_ro_build,
        build_lib.BuildVersionKey.ANDROID_BUILD_VERSION: android_build,
        build_lib.BuildVersionKey.TESTBED_BUILD_VERSION: testbed_build,
        'num': self.num,
        'pool': self.pool,
        'priority': self.priority,
        'timeout': self.timeout,
        'timeout_mins': _JOB_MAX_RUNTIME_MINS_DEFAULT,
        'max_runtime_mins': _JOB_MAX_RUNTIME_MINS_DEFAULT,
        'no_wait_for_results': not self.job_retry,
        'test_source_build': test_source_build,
        'job_retry': self.job_retry,
        'no_delay': self.no_delay,
        'force': self.force,
        'run_prod_code': run_prod_code,
        'is_skylab': is_skylab,
    }

    task_executor.push(task_executor.SUITES_QUEUE, **suite_job_parameters)
    logging.info('Pushing task %r into taskqueue', suite_job_parameters)
    self.is_pushed = True

  def _check_model(self, models_by_board, board, passed_model):
    """Check whether this task should be run on the passed-in model.

    Args:
      models_by_board: The mapping from board to its models.
      board: The board to check whether to run the task.
      passed_model: the model to check whether to run the task.

    Returns:
      A list of valid model to run the task.
    """
    if passed_model is None:
      logging.debug('Model is not set. Run the task with empty model.')
      return [None]

    all_models = models_by_board.get(board, [])
    if passed_model not in all_models:
      logging.debug('Model %s is not in valid model list %s', passed_model,
                    all_models)
      return []

    full_model_name = build_lib.to_full_model(board, passed_model)
    if self.exclude_models and full_model_name in self.exclude_models:
      logging.debug('Model %s is in exclude model list %s', passed_model,
                    self.exclude_models)
      return []

    if self.models and full_model_name not in self.models:
      logging.debug('Model %s is not in support model list %s', passed_model,
                    self.models)
      return []

    return [passed_model]

  def _schedule_cros_builds(self, build_dict, lab_config, db_client):
    """Schedule tasks with branch builds.

    Args:
      build_dict: the build dict for ChromeOS boards, see return
        value of |build_lib.get_cros_builds_since_date_from_db|.
      lab_config: a config.LabConfig object, to read lab config file.
      db_client: a cloud_sql_client.CIDBClient object to connect to cidb.
    """
    models_by_board = lab_config.get_cros_model_map() if lab_config else {}
    skylab_boards = lab_config.get_skylab_board_list() if lab_config else []
    skylab_suites = lab_config.get_skylab_suite_list() if lab_config else []
    logging.info('Skylab_boards: %r', skylab_boards)
    logging.info('Skylab suites: %r', skylab_suites)
    for (board, passed_model, build_type,
         milestone), manifest in build_dict.iteritems():
      cros_build = str(build_lib.CrOSBuild(board, build_type, milestone,
                                           manifest))
      logging.info('Running %s on %s', self.name, cros_build)
      if self.exclude_boards and board in self.exclude_boards:
        logging.debug('Board %s is in excluded board list: %s',
                      board, self.exclude_boards)
        continue

      if self.boards and board not in self.boards:
        logging.debug('Board %s is not in supported board list: %s',
                      board, self.boards)
        continue

      # Check the fitness of the build's branch for task
      branch_build_spec = _pick_branch(build_type, milestone)
      if not self._fits_spec(branch_build_spec):
        logging.debug("branch_build spec %s doesn't fit this task's "
                      "requirement: %s", branch_build_spec, self.branch_specs)
        continue

      firmware_rw_build = None
      firmware_ro_build = None
      if self.firmware_rw_build_spec or self.firmware_ro_build_spec:
        firmware_rw_build = self._get_firmware_build(
            self.firmware_rw_build_spec, board, lab_config, db_client)
        firmware_ro_build = self._get_firmware_build(
            self.firmware_ro_build_spec, board, lab_config, db_client)

      if not firmware_ro_build and self.firmware_ro_build_spec:
        logging.debug('No firmware ro build to run, skip running')
        continue

      if self.test_source == build_lib.BuildType.FIRMWARE_RW:
        test_source_build = firmware_rw_build
      else:
        # Default test source build to CrOS build if it's not specified.
        # Past versions chose based on run_prod_code, but we no longer respect
        # that option and scheduler settings should always set it to False.
        test_source_build = cros_build

      is_skylab = (board in skylab_boards) and (self.suite in skylab_suites)

      for model in self._check_model(models_by_board, board, passed_model):
        self._push_suite(
            board=board,
            model=model,
            cros_build=cros_build,
            firmware_rw_build=firmware_rw_build,
            firmware_ro_build=firmware_ro_build,
            test_source_build=test_source_build,
            is_skylab=is_skylab)

  def _schedule_launch_control_builds(self, launch_control_builds):
    """Schedule tasks with launch control builds.

    Args:
      launch_control_builds: the build dict for Android boards.
    """
    for board, launch_control_build in launch_control_builds.iteritems():
      logging.debug('Running %s on %s', self.name, board)
      if self.exclude_boards and board in self.exclude_boards:
        logging.debug('Board %s is in excluded board list: %s',
                      board, self.exclude_boards)
        continue
      if self.boards and board not in self.boards:
        logging.debug('Board %s is not in supported board list: %s',
                      board, self.boards)
        continue

      for android_build in launch_control_build:
        if not any([branch in android_build
                    for branch in self.launch_control_branches]):
          logging.debug('Branch %s is not required to run for task '
                        '%s', android_build, self.name)
          continue

        self._push_suite(board=board,
                         test_source_build=android_build,
                         launch_control_build=android_build)


def _pick_branch(build_type, milestone):
  """Select branch based on build type.

  If the build_type is a bare branch, return build_type as the build spec.
  If the build_type is a normal CrOS branch, return milestone as the build
  spec.

  Args:
    build_type: a string builder name, like 'release'.
    milestone: a string milestone, like '55'.

  Returns:
    A string milestone if build_type represents CrOS build, otherwise
    return build_type.
  """
  return build_type if build_type in build_lib.BARE_BRANCHES else milestone
